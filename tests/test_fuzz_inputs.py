"""Fuzz tests for malformed inputs to parse_sr16 and parse_snes9x.

Each case produces a synthetically corrupted blob and verifies the parser
either:
  (a) raises ``ValueError`` with a meaningful message, or
  (b) accepts it (with optional warning) and returns a sane structure.

The goal is to catch silent corruption where parsing appears to succeed but
produces a truncated chunk map.
"""
from __future__ import annotations
import gzip
import pytest

from converter.common.format.sr16 import (
    MARKER_KEYS, MARKER_LEN, SR16_MAGIC, parse_sr16,
)
from converter.common.format.snes9x import (
    SNES9X_HEADER, parse_snes9x, write_chunk,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encode_marker(plain: str) -> bytes:
    """Inverse of decode_marker — duplicates test_marker_codec helper to keep
    this file standalone."""
    assert len(plain) == MARKER_LEN
    out = bytearray(MARKER_LEN)
    for i, ch in enumerate(plain):
        b = ord(ch)
        if i == 0 or b == 0:
            out[i] = b
        else:
            out[i] = b ^ MARKER_KEYS[i]
    return bytes(out)


def _build_sr16(*sections: tuple[str, bytes]) -> bytes:
    """Build a minimal SR16 blob with the given sections."""
    out = bytearray(SR16_MAGIC)
    for code, data in sections:
        marker = _encode_marker(f"{code}_{len(data):06d}_")
        out += marker + data
    return bytes(out)


def _build_snes9x(*chunks: tuple[str, bytes]) -> bytes:
    """Build a minimal snes9x save with the given chunks."""
    out = bytearray(SNES9X_HEADER)
    for name, data in chunks:
        out += write_chunk(name, data)
    return bytes(out)


# ---------------------------------------------------------------------------
# parse_sr16 fuzz
# ---------------------------------------------------------------------------

def test_sr16_missing_magic():
    with pytest.raises(ValueError, match="@sgnes@"):
        parse_sr16(b"NOT_AN_SR16_FILE_AT_ALL_OOPS")


def test_sr16_unknown_version_warns_but_parses():
    blob = _build_sr16(("C01", b"\x00" * 161))
    blob = b"@sgnes@007\n" + blob[len(SR16_MAGIC):]
    with pytest.warns(UserWarning, match="unrecognized format version"):
        save = parse_sr16(blob)
    assert save.by_code("C01") is not None


def test_sr16_unknown_version_missing_newline():
    blob = b"@sgnes@9999999"  # no newline within the version-window
    with pytest.raises(ValueError, match="missing newline"):
        parse_sr16(blob)


def test_sr16_truncated_strict_raises():
    blob = _build_sr16(("C01", b"\x00" * 161))
    blob = blob[:-10]  # drop last 10 bytes of C01 data
    with pytest.raises(ValueError, match="truncated section"):
        parse_sr16(blob)


def test_sr16_truncated_lenient_warns_drops_section():
    full = _build_sr16(("C01", b"\x11" * 161), ("P01", b"\x22" * 2645))
    # Truncate inside P01 data
    truncated = full[:len(full) - 100]
    with pytest.warns(UserWarning, match="truncated"):
        save = parse_sr16(truncated, lenient=True)
    # C01 still present, P01 dropped
    assert save.by_code("C01") is not None
    assert save.by_code("P01") is None


def test_sr16_empty_after_magic_returns_no_sections():
    save = parse_sr16(SR16_MAGIC)
    assert save.sections == []
    assert save.trailer == b""


def test_sr16_garbage_marker_breaks_cleanly():
    """Marker that doesn't decode to NNN_NNNNNN_ should stop parsing without
    raising — the stream may legitimately end with non-section bytes."""
    blob = _build_sr16(("C01", b"\x00" * 161)) + b"\x99\xAB\xCD\xEF"
    save = parse_sr16(blob)
    assert save.by_code("C01") is not None
    assert len(save.trailer) == 4  # garbage stays in trailer


def test_sr16_section_with_zero_size():
    blob = _build_sr16(("X00", b""), ("Y01", b"abc"))
    save = parse_sr16(blob)
    assert save.by_code("X00").data == b""
    assert save.by_code("Y01").data == b"abc"


# ---------------------------------------------------------------------------
# parse_snes9x fuzz
# ---------------------------------------------------------------------------

def test_snes9x_no_header_newline():
    with pytest.raises(ValueError, match="missing header newline"):
        parse_snes9x(b"#!s9xsnp:0012")  # no \n


def test_snes9x_corrupt_gzip():
    # Looks gzip but isn't.
    with pytest.raises(ValueError, match="gzip"):
        parse_snes9x(b"\x1f\x8b" + b"definitely not a gzip stream")


def test_snes9x_truncated_chunk_data_raises():
    body = SNES9X_HEADER + b"ABC:000010:short"  # declared 10, only 5 bytes
    with pytest.raises(ValueError, match="truncated"):
        parse_snes9x(body)


def test_snes9x_malformed_chunk_header_raises():
    body = SNES9X_HEADER + b"ABCD000010:" + b"\x00" * 10  # missing first ":"
    with pytest.raises(ValueError, match="malformed chunk header"):
        parse_snes9x(body)


def test_snes9x_non_numeric_size_raises():
    body = SNES9X_HEADER + b"ABC:NOTNUM:" + b"\x00" * 10
    with pytest.raises(ValueError, match="non-numeric size"):
        parse_snes9x(body)


def test_snes9x_missing_trailing_colon_raises():
    body = SNES9X_HEADER + b"ABC:000010X" + b"\x00" * 10  # 'X' not ':'
    with pytest.raises(ValueError, match="missing trailing"):
        parse_snes9x(body)


def test_snes9x_trailing_bytes_warns():
    # < 11 bytes of trailing junk falls through the i+11<=len(blob) guard and
    # triggers the warning. Longer junk would parse as a malformed chunk
    # header (covered by test_snes9x_malformed_chunk_header_raises).
    body = _build_snes9x(("ABC", b"data")) + b"junk"
    with pytest.warns(UserWarning, match="trailing"):
        chunks = parse_snes9x(body)
    assert chunks == {"ABC": b"data"}


def test_snes9x_gzip_roundtrip_strict():
    body = _build_snes9x(("AAA", b"x"), ("BBB", b"yy"))
    chunks = parse_snes9x(gzip.compress(body))
    assert chunks == {"AAA": b"x", "BBB": b"yy"}


# ---------------------------------------------------------------------------
# build_snes9x template-mode validation
# ---------------------------------------------------------------------------

class _FakeSection:
    """Minimal duck-typed SR16Section for build_snes9x validation tests."""
    def __init__(self, code: str, data: bytes):
        self.code = code
        self.data = data
        self.size = len(data)
        self.offset = 0


class _FakeSR16:
    def __init__(self, sections):
        self.sections = sections
        self.source_name = "fake"

    def by_code(self, code):
        for s in self.sections:
            if s.code == code:
                return s
        return None


def test_build_snes9x_missing_template_chunk_raises():
    from converter.sr16_to_snes9x.pipeline import build_snes9x
    sr16 = _FakeSR16([])
    with pytest.raises(ValueError, match="missing required chunk"):
        build_snes9x(sr16, template_chunks={"CPU": b""})  # missing REG/PPU/...


def test_build_snes9x_template_ram_missing_raises():
    from converter.sr16_to_snes9x.pipeline import build_snes9x
    from converter.common.constants import (
        SNES_CPU_SIZE, SNES_REG_SIZE, SNES_PPU_SIZE, SNES_DMA_SIZE,
    )
    chunks = {
        "CPU": b"\x00" * SNES_CPU_SIZE,
        "REG": b"\x00" * SNES_REG_SIZE,
        "PPU": b"\x00" * SNES_PPU_SIZE,
        "DMA": b"\x00" * SNES_DMA_SIZE,
        "SND": b"\x00" * 4,
        "CTL": b"\x00" * 4,
        "TIM": b"\x00" * 4,
    }
    sr16 = _FakeSR16([])  # no SR16 sections so VR1 check fails first
    with pytest.raises(ValueError, match="(RAM chunk|VR1|missing)"):
        build_snes9x(sr16, chunks, use_template_ram=True)
