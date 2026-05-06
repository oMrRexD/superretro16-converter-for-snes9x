"""snes9x PPU(2652B) -> SR16 P01(2645B) reverse field remapper.

Reverse of ``converter.sr16_to_snes9x.state.ppu_remap.remap_p01_to_ppu``.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from converter.common.constants import SNES_PPU_SIZE, SR16_P01_SIZE
from converter.sr16_to_snes9x.state.ppu_remap import SNES9X_LAYOUT, sr16_name

_CONVERTER_ROOT = Path(__file__).resolve().parents[2]
_TABLE_PATH = _CONVERTER_ROOT / "sr16_to_snes9x" / "state" / "freezedata.json"


@lru_cache(maxsize=1)
def load_sr16_p01_index() -> dict[str, dict]:
    """Load the SR16 P01 field index shared by reverse PPU/palette code."""
    with _TABLE_PATH.open(encoding="utf-8") as f:
        d = json.load(f)
    return {e["name"]: e for e in d["p01"]}


def build_p01(ppu: bytes) -> bytes:
    """Build SR16 P01 section (2645B) from snes9x PPU chunk (2652B).

    Walks the snes9x SnapPPU layout in order, copies each field to the
    corresponding SR16 FreezeData offset in the P01 blob.
    """
    if len(ppu) != SNES_PPU_SIZE:
        raise ValueError(f"PPU chunk size {len(ppu)} != {SNES_PPU_SIZE}")

    sr16_index = load_sr16_p01_index()
    out = bytearray(SR16_P01_SIZE)
    s9x_cur = 0

    for s9x_name, s9x_size in SNES9X_LAYOUT:
        sr_name = sr16_name(s9x_name)
        e = sr16_index.get(sr_name)
        if e is not None:
            sr_off = e["serial_off"]
            sr_size = e["serial_size"]

            if sr_size == s9x_size:
                out[sr_off:sr_off + sr_size] = ppu[s9x_cur:s9x_cur + s9x_size]
            elif sr_size > s9x_size:
                # SR16 has wider field: zero-pad MSB, write snes9x into low bytes.
                out[sr_off + sr_size - s9x_size:sr_off + sr_size] = (
                    ppu[s9x_cur:s9x_cur + s9x_size]
                )
            else:
                # SR16 narrower: take only the low bytes from snes9x.
                out[sr_off:sr_off + sr_size] = (
                    ppu[s9x_cur + s9x_size - sr_size:s9x_cur + s9x_size]
                )
        s9x_cur += s9x_size

    # --- Post-remap corrections (reverse of forward) ---

    # 1. Brightness: snes9x 0-15 → SR16 1-16 (add 1)
    for name, sz in SNES9X_LAYOUT:
        sr_name_n = sr16_name(name)
        e = sr16_index.get(sr_name_n)
        if name == "Brightness" and e is not None:
            sr_off = e["serial_off"]
            sr_size = e["serial_size"]
            # SR16 stores Brightness as 2B BE; only low byte matters.
            val = out[sr_off + sr_size - 1]
            out[sr_off + sr_size - 1] = min(16, val + 1)

        # 2. ClipWindow Inside → Outside: invert values
        if ("ClipWindow1Inside" in name or "ClipWindow2Inside" in name) and e is not None:
            sr_off = e["serial_off"]
            out[sr_off] = 1 if out[sr_off] == 0 else 0

    # 3. RecomputeClipWindows: SR16 expects this flag set to 1 so it recalculates
    #    window masks on resume. snes9x stores 0 after recalculation.
    e = sr16_index.get("RecomputeClipWindows")
    if e is not None:
        out[e["serial_off"]] = 1

    # 4. Need16x8Mulitply: typo preserved from old snes9x/SR16 FreezeData.
    #    SR16 uses this flag; set to 1 for safe resume.
    e = sr16_index.get("Need16x8Mulitply")
    if e is not None:
        out[e["serial_off"]] = 1

    return bytes(out)
