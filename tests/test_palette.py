"""Tests for palette helpers and WRAM SNES address mapping."""
from __future__ import annotations

from converter.sr16_to_snes9x.state.palette import (
    _wram_read,
    _decode_sr16_display_cgram,
    _palette_values_be, _palette_values_le, _palette_values_rgb565_to_snes,
    _palette_stats, _plausible_palette,
    _build_sho_from_sr16_png,
)
from converter.common.constants import (
    SR16_SCREEN_BYTES, SR16_SCREEN_WIDTH, SR16_SCREEN_HEIGHT,
    SHO_DATA_BYTES, CGRAM_BYTES, CGRAM_ENTRIES, PPU_OFF_CGDATA,
)


# ---------------------------------------------------------------------------
# _wram_read SNES address mapping
# ---------------------------------------------------------------------------

def test_wram_read_low_bank_7e():
    wram = bytes(range(256)) + b"\x00" * (0x20000 - 256)
    assert _wram_read(wram, 0x7E0010, 4) == bytes([0x10, 0x11, 0x12, 0x13])


def test_wram_read_high_bank_7f():
    wram = b"\x00" * 0x10000 + bytes(range(256)) + b"\x00" * (0x10000 - 256)
    assert _wram_read(wram, 0x7F0005, 3) == bytes([5, 6, 7])


def test_wram_read_low_mirror_in_bank_00():
    wram = bytes([0xAA] * 0x100) + b"\x00" * (0x20000 - 0x100)
    assert _wram_read(wram, 0x000050, 4) == b"\xaa\xaa\xaa\xaa"


def test_wram_read_low_mirror_in_bank_80():
    wram = bytes([0xBB] * 0x100) + b"\x00" * (0x20000 - 0x100)
    assert _wram_read(wram, 0x800010, 2) == b"\xbb\xbb"


def test_wram_read_outside_wram_returns_empty():
    wram = b"\x00" * 0x20000
    # ROM bank, high address: not in any WRAM mirror.
    assert _wram_read(wram, 0x008000, 16) == b""
    assert _wram_read(wram, 0xC00000, 4) == b""


def test_wram_read_short_wram_safe():
    wram = b"\x01\x02"
    # Asking past the end returns whatever is available (slice semantics).
    assert _wram_read(wram, 0x7E0000, 4) == b"\x01\x02"


# ---------------------------------------------------------------------------
# Palette value parsers
# ---------------------------------------------------------------------------

def test_palette_values_le_and_be_roundtrip():
    # Choose 256 distinct 15-bit values
    vals = [i & 0x7FFF for i in range(CGRAM_ENTRIES)]
    le_blob = b"".join(v.to_bytes(2, "little") for v in vals)
    be_blob = b"".join(v.to_bytes(2, "big") for v in vals)
    assert _palette_values_le(le_blob) == vals
    assert _palette_values_be(be_blob) == vals
    assert len(le_blob) == CGRAM_BYTES
    assert len(be_blob) == CGRAM_BYTES


def test_palette_rgb565_to_snes_swap_red_blue():
    # RGB565 layout: rrrrrggg gggbbbbb
    # SNES BGR555:   _bbbbbgg gggrrrrr
    # An all-red RGB565 0xF800 should become red bits in SNES.
    snes = _palette_values_rgb565_to_snes([0xF800])
    assert snes == [0x001F]   # red=31, green=0, blue=0
    snes = _palette_values_rgb565_to_snes([0x001F])
    assert snes == [0x7C00]   # blue=31


def test_palette_rgb565_to_snes_green_channel():
    # RGB565 green is 6 bits (0xFFE0 = bits 5..10). Converter takes the
    # top 5 bits (`(value >> 6) & 0x1F`), so 0x07E0 -> green=0x1F (5 MSB
    # of 0x3F) -> SNES green at bits 5..9.
    snes = _palette_values_rgb565_to_snes([0x07E0])
    assert snes == [0x03E0]   # green=31 in SNES


def test_palette_rgb565_to_snes_white_and_black():
    # Pure white in RGB565 (all bits set in each channel): 0xFFFF.
    # SNES white is 0x7FFF (bit 15 reserved).
    snes = _palette_values_rgb565_to_snes([0xFFFF])
    # Green keeps top 5 of 6 bits => still all 1s in 5-bit form.
    assert snes == [0x7FFF]
    snes = _palette_values_rgb565_to_snes([0x0000])
    assert snes == [0x0000]


def test_palette_rgb565_to_snes_mixed_colors():
    # Half red + quarter green: rgb565 r=0x10 (16), g=0x10 (16), b=0
    # => value = (16 << 11) | (16 << 6) = 0x8400
    # SNES gets red=16, green=16 (top 5 of 16=0b10000), blue=0
    snes = _palette_values_rgb565_to_snes([0x8400])
    assert snes == [16 | (16 << 5)]  # red=16, green=16


def test_palette_rgb565_to_snes_roundtrip_does_not_set_high_bit():
    # Bit 15 of SNES BGR555 is reserved. The converter must never set it
    # even if RGB565 had its low blue bit ambiguously located.
    for src in (0xFFFF, 0x8000, 0x8001, 0x801F):
        out = _palette_values_rgb565_to_snes([src])
        assert (out[0] & 0x8000) == 0, f"high bit leaked for {src:#06x}"


def test_decode_sr16_display_cgram_uses_rgb565_palette_cache():
    ppu = bytearray(PPU_OFF_CGDATA + CGRAM_BYTES)
    rgb565_values = [0xF800, 0x07E0, 0x001F] + [0] * (CGRAM_ENTRIES - 3)
    for i, value in enumerate(rgb565_values):
        ppu[PPU_OFF_CGDATA + i * 2:PPU_OFF_CGDATA + i * 2 + 2] = (
            value.to_bytes(2, "big")
        )
    pixels = (
        (0xF800).to_bytes(2, "little") * 64
        + (0x07E0).to_bytes(2, "little") * 64
        + (0x001F).to_bytes(2, "little") * 64
    )
    png = pixels + b"\x00\x00" * (SR16_SCREEN_WIDTH * SR16_SCREEN_HEIGHT - 192)

    assert _decode_sr16_display_cgram(ppu, png)

    decoded = _palette_values_be(
        ppu[PPU_OFF_CGDATA:PPU_OFF_CGDATA + CGRAM_BYTES]
    )
    assert decoded[:3] == [0x001F, 0x03E0, 0x7C00]


def test_decode_sr16_display_cgram_leaves_raw_snes_palette_when_it_matches():
    ppu = bytearray(PPU_OFF_CGDATA + CGRAM_BYTES)
    snes_values = [0x001F, 0x03E0, 0x7C00] + [0] * (CGRAM_ENTRIES - 3)
    for i, value in enumerate(snes_values):
        ppu[PPU_OFF_CGDATA + i * 2:PPU_OFF_CGDATA + i * 2 + 2] = (
            value.to_bytes(2, "big")
        )
    pixels = (
        (0xF800).to_bytes(2, "little") * 64
        + (0x07E0).to_bytes(2, "little") * 64
        + (0x001F).to_bytes(2, "little") * 64
    )
    png = pixels + b"\x00\x00" * (SR16_SCREEN_WIDTH * SR16_SCREEN_HEIGHT - 192)

    assert not _decode_sr16_display_cgram(ppu, png)
    assert _palette_values_be(
        ppu[PPU_OFF_CGDATA:PPU_OFF_CGDATA + CGRAM_BYTES]
    )[:3] == snes_values[:3]


# ---------------------------------------------------------------------------
# Palette stats / plausibility
# ---------------------------------------------------------------------------

def test_plausible_palette_for_realistic_rgb_distribution():
    import random
    rng = random.Random(42)
    vals = [
        ((rng.randrange(32) << 10) | (rng.randrange(32) << 5) | rng.randrange(32))
        for _ in range(256)
    ]
    stats = _palette_stats(vals)
    # Random colors should be plausible (no high bits, broad palette, balanced)
    assert _plausible_palette(stats)


def test_implausible_high_bit_palette():
    # All entries with bit 15 set — clearly bogus
    vals = [(0x8000 | i) for i in range(256)]
    stats = _palette_stats(vals)
    assert stats["high_bits"] == 256
    assert not _plausible_palette(stats)


def test_implausible_dominant_channel():
    # All red — dominance 1.0
    vals = [0x001F] * 256
    stats = _palette_stats(vals)
    assert stats["dominance"] == 1.0
    assert not _plausible_palette(stats)


# ---------------------------------------------------------------------------
# SHO screenshot embedding
# ---------------------------------------------------------------------------

def test_sho_returns_none_for_wrong_size():
    assert _build_sho_from_sr16_png(None) is None
    assert _build_sho_from_sr16_png(b"") is None
    assert _build_sho_from_sr16_png(b"\x00" * 1024) is None


def test_sho_basic_shape():
    png = b"\x00\x00" * (SR16_SCREEN_WIDTH * SR16_SCREEN_HEIGHT)
    sho = _build_sho_from_sr16_png(png)
    assert sho is not None
    # 5-byte header + RGB data
    expected_len = 5 + SHO_DATA_BYTES
    assert len(sho) == expected_len
    # Header: width(2 BE) height(2 BE) interlaced(1)
    assert sho[0:2] == SR16_SCREEN_WIDTH.to_bytes(2, "big")
    assert sho[2:4] == SR16_SCREEN_HEIGHT.to_bytes(2, "big")
    assert sho[4] == 0


def test_sho_pixel_extraction():
    # Single pure-red pixel (RGB565 0xF800) followed by zeros.
    px = (0xF800).to_bytes(2, "little")
    png = px + b"\x00\x00" * (SR16_SCREEN_WIDTH * SR16_SCREEN_HEIGHT - 1)
    sho = _build_sho_from_sr16_png(png)
    # First RGB triple after the 5-byte header
    body_off = 5
    r, g, b = sho[body_off], sho[body_off + 1], sho[body_off + 2]
    assert (r, g, b) == (0x1F, 0, 0)
