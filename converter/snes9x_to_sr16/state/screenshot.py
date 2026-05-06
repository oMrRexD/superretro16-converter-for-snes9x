"""snes9x SHO → SR16 PNG section (256×224 RGB565 framebuffer).

SR16's 'PNG' section is actually a raw 256×224 RGB565 LE framebuffer, not
a compressed PNG image.

The reverse converter intentionally uses the SHO screenshot chunk already
stored inside the snes9x snapshot.  It must not render the ROM in an emulator
just to synthesize a SuperRetro16 thumbnail.
"""
from __future__ import annotations

from converter.common.constants import (
    SR16_SCREEN_WIDTH, SR16_SCREEN_HEIGHT, SR16_SCREEN_BYTES,
    SHO_DATA_BYTES,
)


def build_png_from_sho(sho: bytes) -> bytes | None:
    """Convert snes9x SHO screenshot to SR16 PNG (256×224 RGB565 LE).

    SHO layout:
      [0:2]   Width  (u16 BE)
      [2:4]   Height (u16 BE)
      [4]     Interlace flag (u8)
      [5:5+734208]  Pixels — fixed backing store, each channel 5-bit (0-31)

    The forward converter writes SHO channels as:
      byte[0] = (rgb565 >> 11) & 0x1F  → R5
      byte[1] = (rgb565 >>  6) & 0x1F  → G5 (top 5 of 6-bit green)
      byte[2] =  rgb565        & 0x1F  → B5

    Returns 114688 bytes (256 × 224 × 2) or None on failure.
    """
    expected_size = 5 + SHO_DATA_BYTES  # 734213
    if sho is None or len(sho) < expected_size:
        return None

    width = int.from_bytes(sho[0:2], "big")
    height = int.from_bytes(sho[2:4], "big")

    if width == 0 or height == 0:
        return None

    pixel_data = sho[5:5 + SHO_DATA_BYTES]

    out = bytearray(SR16_SCREEN_BYTES)
    dst_w = SR16_SCREEN_WIDTH   # 256
    dst_h = SR16_SCREEN_HEIGHT  # 224

    x_scale = max(1, width // dst_w)
    y_scale = max(1, height // dst_h)

    for y in range(dst_h):
        src_y = min(y * y_scale, height - 1)
        for x in range(dst_w):
            src_x = min(x * x_scale, width - 1)
            src_off = (src_y * width + src_x) * 3
            if src_off + 2 >= len(pixel_data):
                continue
            r5 = pixel_data[src_off] & 0x1F
            g5 = pixel_data[src_off + 1] & 0x1F
            b5 = pixel_data[src_off + 2] & 0x1F
            g6 = (g5 << 1) | (g5 >> 4)
            rgb565 = (r5 << 11) | (g6 << 5) | b5
            dst_off = (y * dst_w + x) * 2
            out[dst_off] = rgb565 & 0xFF
            out[dst_off + 1] = (rgb565 >> 8) & 0xFF

    return bytes(out)
