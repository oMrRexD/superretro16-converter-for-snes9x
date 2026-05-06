"""Tests for the SR16 11-byte XOR marker codec."""
from __future__ import annotations
import pytest

from converter.common.format.sr16 import (
    MARKER_KEYS, MARKER_LEN, decode_marker, parse_sr16, SR16_MAGIC,
)


# Each chunk marker is 11 bytes:
#   pos 0  : raw section letter
#   pos 1.. : XOR with MARKER_KEYS[i]; bytes that are 0x00 stay 0x00.

def _encode_marker(plain: str) -> bytes:
    """Inverse of decode_marker — used to build synthetic SR16 blobs."""
    assert len(plain) == MARKER_LEN
    out = bytearray(MARKER_LEN)
    for i, ch in enumerate(plain):
        b = ord(ch)
        if i == 0 or b == 0:
            out[i] = b
        else:
            out[i] = b ^ MARKER_KEYS[i]
    return bytes(out)


def test_marker_roundtrip_basic():
    plain = "C01_000161_"
    enc = _encode_marker(plain)
    assert decode_marker(enc) == plain


@pytest.mark.parametrize("code,size", [
    ("C01", 161),
    ("P01", 2645),
    ("D01", 152),
    ("VR1", 65536),
    ("RM1", 131072),
    ("F01", 32768),
    ("A01", 248),
    ("AR1", 65536),
    ("SSZ", 1281),
    ("PSD", 1450),
    ("4XC", 8192),
    ("PNG", 114688),
])
def test_decode_known_section_markers(code, size):
    plain = f"{code}_{size:06d}_"
    assert decode_marker(_encode_marker(plain)) == plain


def test_marker_zero_bytes_stay_zero():
    """Bytes equal to 0x00 are NOT XORed (`eorne` in the ARM impl).

    MARKER_KEYS layout: (None, 3, 6, 5, 0xC, 0xF, 0xA, 9, 0x18, 0x1B, 0x1E).
    """
    raw = bytes([ord("A"), 0, 5, 0, 0xFF, 0, 0, 0, 0, 0, 0])
    decoded = decode_marker(raw)
    assert decoded[0] == "A"
    assert decoded[1] == "\x00"           # zero stays zero
    assert decoded[2] == chr(5 ^ 6)       # key[2] = 6
    assert decoded[3] == "\x00"           # zero stays zero
    assert decoded[4] == chr(0xFF ^ 0xC)  # key[4] = 0xC


def test_marker_wrong_size_raises():
    with pytest.raises(ValueError):
        decode_marker(b"too short")


def test_parse_sr16_rejects_bad_magic():
    with pytest.raises(ValueError):
        parse_sr16(b"not an sr16 file")


def test_parse_sr16_handles_empty_after_magic():
    save = parse_sr16(SR16_MAGIC)
    assert save.sections == []
    assert save.trailer == b""


def test_parse_sr16_minimal_section():
    payload = b"hello world!"   # 12 bytes
    marker = _encode_marker(f"XYZ_{len(payload):06d}_")
    blob = SR16_MAGIC + marker + payload
    save = parse_sr16(blob, source_name="test.s01")
    assert len(save.sections) == 1
    section = save.sections[0]
    assert section.code == "XYZ"
    assert section.size == len(payload)
    assert section.data == payload
    assert save.source_name == "test.s01"
    assert save.by_code("XYZ") is section
    assert save.by_code("ABC") is None


def test_parse_sr16_multiple_sections():
    pa = b"\x01\x02\x03\x04"
    pb = b"\xff" * 7
    blob = (
        SR16_MAGIC
        + _encode_marker(f"AAA_{len(pa):06d}_") + pa
        + _encode_marker(f"BBB_{len(pb):06d}_") + pb
    )
    save = parse_sr16(blob)
    assert [s.code for s in save.sections] == ["AAA", "BBB"]
    assert save.by_code("BBB").data == pb


def test_parse_sr16_truncated_data_raises():
    marker = _encode_marker("XYZ_000016_")
    blob = SR16_MAGIC + marker + b"only_eight"
    with pytest.raises(ValueError):
        parse_sr16(blob)


def test_parse_sr16_keeps_trailer():
    # If a trailing byte fails to look like a marker, parse stops and trailer
    # captures the rest.
    pa = b"abcd"
    blob = (
        SR16_MAGIC
        + _encode_marker(f"AAA_{len(pa):06d}_") + pa
        + b"\x00" * MARKER_LEN  # invalid marker (no underscores)
    )
    save = parse_sr16(blob)
    assert len(save.sections) == 1
    assert save.trailer == b"\x00" * MARKER_LEN
