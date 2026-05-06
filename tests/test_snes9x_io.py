"""Tests for snes9x numeric-slot chunk container I/O."""
from __future__ import annotations
import gzip
import pytest

from converter.common.format.snes9x import (
    SNES9X_HEADER, SNES9X_VERSION, write_chunk, parse_snes9x,
)


def test_header_shape():
    assert SNES9X_HEADER.startswith(b"#!s9xsnp:")
    assert SNES9X_HEADER.endswith(b"\n")
    assert SNES9X_VERSION in SNES9X_HEADER


def test_write_chunk_shape():
    out = write_chunk("ABC", b"hello")
    # "ABC:000005:" + payload
    assert out == b"ABC:000005:hello"


def test_write_chunk_zero_size():
    out = write_chunk("ZRO", b"")
    assert out == b"ZRO:000000:"


def test_write_chunk_rejects_bad_name():
    with pytest.raises(ValueError):
        write_chunk("AB", b"x")
    with pytest.raises(ValueError):
        write_chunk("ABCD", b"x")


def test_write_then_parse_roundtrip():
    body = SNES9X_HEADER
    body += write_chunk("AAA", b"\x01\x02\x03")
    body += write_chunk("BBB", b"\x00" * 10)
    chunks = parse_snes9x(body)
    assert chunks == {"AAA": b"\x01\x02\x03", "BBB": b"\x00" * 10}


def test_parse_snes9x_accepts_gzip():
    body = SNES9X_HEADER + write_chunk("ABC", b"data")
    gzipped = gzip.compress(body)
    chunks = parse_snes9x(gzipped)
    assert chunks == {"ABC": b"data"}


def test_parse_snes9x_handles_empty_chunks_list():
    chunks = parse_snes9x(SNES9X_HEADER)
    assert chunks == {}


def test_parse_snes9x_negative_size_marker():
    """Some snes9x outputs use a `-XX` size prefix with a 4-byte BE size.

    We synthesize one by hand and confirm the parser reads the BE length.
    """
    payload = b"\xab" * 0x100
    # Format: "ABC:-XX1234:" where 1234 are 4 bytes BE int, X is filler digit
    marker = b"ABC:-X" + (0x100).to_bytes(4, "big") + b":"
    blob = SNES9X_HEADER + marker + payload
    chunks = parse_snes9x(blob)
    assert chunks == {"ABC": payload}
