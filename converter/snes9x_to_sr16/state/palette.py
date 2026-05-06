"""snes9x CGRAM (BGR555 BE) -> SR16 CGRAM (RGB565 display-cache).

Reverse of ``converter.sr16_to_snes9x.state.palette._decode_sr16_display_cgram``.
"""
from __future__ import annotations

from converter.common.constants import PPU_OFF_CGDATA, CGRAM_BYTES
from .ppu import load_sr16_p01_index


def bgr555_to_rgb565(bgr555: int) -> int:
    """Convert a single SNES BGR555 value to SR16's RGB565 display format.

    SNES BGR555 (15-bit):  0BBBBBGG GGGRRRRR
    SR16 RGB565 (16-bit):  RRRRRGGG GGGBBBBB
    """
    r5 = bgr555 & 0x1F
    g5 = (bgr555 >> 5) & 0x1F
    b5 = (bgr555 >> 10) & 0x1F
    # Scale green from 5-bit to 6-bit (approximate: shift left and copy MSB)
    g6 = (g5 << 1) | (g5 >> 4)
    return (r5 << 11) | (g6 << 5) | b5


def encode_cgram_to_sr16(ppu: bytes) -> bytearray:
    """Convert snes9x PPU CGDATA (512B, BE uint16[256]) to SR16 RGB565 BE.

    The returned bytearray can be written back into the PPU bytes at
    PPU_OFF_CGDATA for the P01 remap, or applied separately.

    Returns 512 bytes of RGB565 big-endian palette data.

    SR16's framebuffer-like PNG section is little-endian RGB565, but P01's
    serialized CGDATA cache is read by the forward converter as big-endian
    RGB565 after the raw P01->PPU field remap. Writing it little-endian makes
    roundtripped palettes decode as unrelated colors.
    """
    cgdata = ppu[PPU_OFF_CGDATA:PPU_OFF_CGDATA + CGRAM_BYTES]
    out = bytearray(CGRAM_BYTES)

    for i in range(256):
        # snes9x CGDATA is serialized as 2B big-endian per entry.
        bgr555 = (cgdata[i * 2] << 8) | cgdata[i * 2 + 1]
        bgr555 &= 0x7FFF  # mask bit 15 (should be 0 in valid SNES data)
        rgb565 = bgr555_to_rgb565(bgr555)
        out[i * 2] = (rgb565 >> 8) & 0xFF
        out[i * 2 + 1] = rgb565 & 0xFF

    return out


def patch_p01_cgdata_as_rgb565(p01: bytearray, ppu: bytes) -> None:
    """Overwrite the CGDATA region of P01 with RGB565 display-cache values.

    SR16 normally stores its P01 CGDATA in the renderer-facing RGB565 format.
    After the PPU→P01 remap copies raw BGR555 bytes into P01, this function
    converts them in-place.
    """
    sr16_cgdata = encode_cgram_to_sr16(ppu)
    e = load_sr16_p01_index().get("CGDATA")
    if e is None:
        return
    sr_off = e["serial_off"]
    sr_size = e["serial_size"]
    # SR16's CGDATA should be 512 bytes (256 entries x 2B)
    n = min(sr_size, CGRAM_BYTES)
    p01[sr_off:sr_off + n] = sr16_cgdata[:n]
