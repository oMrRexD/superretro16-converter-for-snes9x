"""SuperRetro16 .s0X binary format: marker codec + section parser.

SuperRetro16 .s0X file structure
--------------------------------
  bytes 0..10  : ASCII magic "@sgnes@006\\n"
  bytes 11..   : sequence of <marker><binary-data> chunks

  marker (11 bytes), per-position XOR-decoded:
    pos 0 : section letter (raw)
    pos 1..10: XOR with keys (3,6,5,0xC,0xF,0xA,9,0x18,0x1B,0x1E)
  Bytes equal to 0 stay 0.

"""
from __future__ import annotations
import warnings
from dataclasses import dataclass

# --- marker codec ---------------------------------------------------------
MARKER_KEYS = (None, 3, 6, 5, 0xC, 0xF, 0xA, 9, 0x18, 0x1B, 0x1E)
MARKER_LEN = 11

def decode_marker(buf: bytes) -> str:
    """Decode an 11-byte SR16 chunk marker. Bytes that are 0x00 are left as 0."""
    if len(buf) != MARKER_LEN:
        raise ValueError("marker must be 11 bytes")
    out = bytearray(MARKER_LEN)
    for i, b in enumerate(buf):
        if i == 0 or b == 0:
            out[i] = b
        else:
            out[i] = b ^ MARKER_KEYS[i]
    return out.decode("latin-1")

# --- SuperRetro16 parsing -------------------------------------------------
SR16_MAGIC = b"@sgnes@006\n"
SR16_MAGIC_PREFIX = b"@sgnes@"   # version-agnostic prefix; suffix is "NNN\n"

@dataclass
class SR16Section:
    code:   str          # decoded 3-letter section code, e.g. "C01", "VR1"
    size:   int          # data length in bytes
    offset: int          # data offset in source file
    data:   bytes

@dataclass
class SR16Save:
    sections: list[SR16Section]
    trailer:  bytes          # bytes after the last marker's declared range
    source_name: str = ""

    def by_code(self, code: str) -> SR16Section | None:
        for s in self.sections:
            if s.code == code:
                return s
        return None

def parse_sr16(blob: bytes, source_name: str = "",
               lenient: bool = False) -> SR16Save:
    """Parse a SuperRetro16 .s0X blob into sections.

    By default, raises ValueError on a truncated trailing section. With
    ``lenient=True`` a truncated trailing section is dropped and a warning
    is emitted instead — useful for partially-written/recovered saves.

    A non-006 ``@sgnes@NNN`` magic emits a warning but does not abort parsing:
    downstream extractors may still succeed if the structural layout is
    unchanged.
    """
    if not blob.startswith(SR16_MAGIC_PREFIX):
        raise ValueError("not a SuperRetro16 save (missing @sgnes@ magic)")
    if not blob.startswith(SR16_MAGIC):
        # Same prefix, different version. Locate the first newline within a
        # short window to honor whichever 'NNN\n' version this build uses.
        nl = blob.find(b"\n", len(SR16_MAGIC_PREFIX), len(SR16_MAGIC_PREFIX) + 8)
        if nl < 0:
            raise ValueError(
                "SR16 save header malformed (missing newline after @sgnes@NNN)"
            )
        version = blob[len(SR16_MAGIC_PREFIX):nl].decode("ascii", "replace")
        warnings.warn(
            f"SR16 save uses unrecognized format version {version!r} "
            "(expected 006); extraction may produce incorrect results",
            stacklevel=2,
        )
        pos = nl + 1
    else:
        pos = len(SR16_MAGIC)
    sections: list[SR16Section] = []
    while pos + MARKER_LEN <= len(blob):
        m = blob[pos:pos+MARKER_LEN]
        decoded = decode_marker(m)
        # decoded looks like "C01_000161_". Do not assume the third byte is
        # "1": late sections such as SSZ, PSD, 4XC, and PNG use the same
        # marker codec.
        if (
            len(decoded) != MARKER_LEN
            or decoded[3] != "_"
            or decoded[10] != "_"
            or not decoded[4:10].isdigit()
        ):
            break
        code = decoded[:3]
        size = int(decoded[4:10])
        data_off = pos + MARKER_LEN
        data = blob[data_off:data_off + size]
        if len(data) != size:
            if lenient:
                warnings.warn(
                    f"SR16 section {code} at {data_off:#x} truncated "
                    f"(declared {size}, got {len(data)}); dropping",
                    stacklevel=2,
                )
                break
            raise ValueError(f"truncated section {code} at {data_off:#x}")
        sections.append(SR16Section(code, size, data_off, data))
        pos = data_off + size
    trailer = blob[pos:]
    return SR16Save(sections, trailer, source_name)
