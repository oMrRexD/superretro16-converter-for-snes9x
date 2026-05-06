"""Binary packing helpers for snes9x SND chunks."""
from __future__ import annotations

import struct

def _be_u(buf: bytes, off: int, size: int) -> int:
    return int.from_bytes(buf[off:off + size], "big")

def _be_s16(buf: bytes, off: int) -> int:
    v = int.from_bytes(buf[off:off + 2], "big")
    return v - 0x10000 if v & 0x8000 else v

def _pack_le_i32(buf: bytearray, off: int, val: int) -> None:
    struct.pack_into("<i", buf, off, val & 0xFFFFFFFF)

def _pack_le_u16(buf: bytearray, off: int, val: int) -> None:
    struct.pack_into("<H", buf, off, val & 0xFFFF)

def _pack_le_i16(buf: bytearray, off: int, val: int) -> None:
    val = max(-32768, min(32767, int(val)))
    struct.pack_into("<h", buf, off, val)
