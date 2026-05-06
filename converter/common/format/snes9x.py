"""snes9x numeric-slot freeze state container I/O.

snes9x freeze state (target)
----------------------------
  Gzipped stream with "#!s9xsnp:0012\\n" header (version 12).
  Chunks: "XXX:NNNNNN:<data>" with big-endian struct fields.
"""
from __future__ import annotations
import gzip
import warnings

# --- snes9x writing -------------------------------------------------------
SNES9X_VERSION = b"0012"
SNES9X_HEADER  = b"#!s9xsnp:" + SNES9X_VERSION + b"\n"

def write_chunk(name: str, data: bytes) -> bytes:
    if len(name) != 3:
        raise ValueError("chunk name must be 3 chars")
    return f"{name}:{len(data):06d}:".encode("ascii") + data

# --- snes9x parsing (used to read --template) -----------------------------
def parse_snes9x(blob: bytes) -> dict[str, bytes]:
    """Return {chunk_name: chunk_data}. Accepts gzipped or plain.

    Raises ValueError on malformed/truncated chunks or corrupt gzip stream.
    Issues a UserWarning via warnings.warn if trailing bytes remain after
    the last well-formed chunk (these are dropped — callers expecting them
    must validate the source separately).
    """
    if blob[:2] == b"\x1f\x8b":
        try:
            blob = gzip.decompress(blob)
        except (gzip.BadGzipFile, OSError, EOFError) as e:
            raise ValueError(
                f"snes9x template is gzip-marked but decompression failed: {e}"
            ) from e
    try:
        nl = blob.index(b"\n")
    except ValueError:
        raise ValueError(
            "snes9x template missing header newline (not a snes9x save?)"
        ) from None
    chunks: dict[str, bytes] = {}
    i = nl + 1
    while i + 11 <= len(blob):
        if blob[i+3:i+4] != b":":
            raise ValueError(
                f"malformed chunk header at offset {i}: expected ':' separator, "
                f"got {bytes(blob[i:i+11])!r}"
            )
        name = blob[i:i+3].decode("ascii", "replace")
        if blob[i+4:i+5] == b"-":
            size = int.from_bytes(blob[i+6:i+10], "big")
        else:
            try:
                size = int(blob[i+4:i+10])
            except ValueError as e:
                raise ValueError(
                    f"chunk {name!r} at offset {i} has non-numeric size: "
                    f"{bytes(blob[i+4:i+10])!r}"
                ) from e
        if blob[i+10:i+11] != b":":
            raise ValueError(
                f"chunk {name!r} at offset {i} missing trailing ':' before data"
            )
        if i + 11 + size > len(blob):
            raise ValueError(
                f"chunk {name!r} at offset {i} truncated: declared size "
                f"{size}, available {len(blob) - i - 11}"
            )
        chunks[name] = blob[i+11:i+11+size]
        i += 11 + size
    if i < len(blob):
        warnings.warn(
            f"snes9x template has {len(blob) - i} trailing bytes after last "
            "chunk — they will be ignored",
            stacklevel=2,
        )
    return chunks
