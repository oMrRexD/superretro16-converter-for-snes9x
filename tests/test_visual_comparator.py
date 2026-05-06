"""Tests for visual artifact classification."""
from __future__ import annotations

from converter.common.constants import SR16_SCREEN_WIDTH, SR16_SCREEN_HEIGHT
from tests.visual_compare_helper import compare_visual


def _rgb565(red: int, green: int, blue: int) -> bytes:
    value = ((red & 0x1F) << 11) | ((green & 0x3F) << 5) | (blue & 0x1F)
    return value.to_bytes(2, "little")


def _frame(fill: bytes | None = None) -> bytearray:
    fill = fill or _rgb565(0, 0, 0)
    return bytearray(fill * (SR16_SCREEN_WIDTH * SR16_SCREEN_HEIGHT))


def _put_rect(buf: bytearray, x: int, y: int, w: int, h: int, color: bytes) -> None:
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            off = (yy * SR16_SCREEN_WIDTH + xx) * 2
            buf[off:off + 2] = color


def test_mild_same_palette_phase_is_not_sprite_glitch():
    """Small phase/scroll differences with the same colors are not corruption."""
    dark = _rgb565(0, 0, 8)
    blue = _rgb565(0, 0, 31)
    ref = _frame(dark)
    emu = _frame(dark)

    for y in range(40, 184, 24):
        _put_rect(ref, 32, y, 48, 8, blue)
        _put_rect(emu, 36, y, 48, 8, blue)

    report = compare_visual(bytes(ref), bytes(emu))

    assert report.high_dist_blocks > 3
    assert not report.palette_error
    assert not report.sprite_glitch


def test_local_damage_still_flags_sprite_glitch():
    ref = _frame()
    emu = _frame()
    _put_rect(emu, 96, 80, 32, 32, _rgb565(31, 63, 31))

    report = compare_visual(bytes(ref), bytes(emu))

    assert report.sprite_glitch
