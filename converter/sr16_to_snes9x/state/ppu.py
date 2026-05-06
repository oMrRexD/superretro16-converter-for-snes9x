"""SR16 P01 -> snes9x v12 PPU extraction + post-load runtime sync."""
from __future__ import annotations
import logging

from converter.common.constants import (
    HDMAEN, MDMAEN,
    DMA_REGS_BASE, DMA_REGS_END, DMA_CH_STRIDE, DMA_OFF_BBAD,
    W12SEL, W34SEL, WOBJSEL, WH0, WH1, WH2, WH3, WBGLOG, WOBJLOG, COLDATA,
    CGRAM_BYTES,
    PPU_OFF_CGADD, PPU_OFF_CG_SAVED_BYTE, PPU_OFF_CGDATA,
    PPU_OFF_WIN1_LEFT, PPU_OFF_WIN1_RIGHT,
    PPU_OFF_WIN2_LEFT, PPU_OFF_WIN2_RIGHT,
    PPU_OFF_RECOMPUTE_CLIP, PPU_OFF_CLIP_BLOCK, PPU_CLIP_SLOT_STRIDE,
    CLIP_OFF_WIN1_ENABLE, CLIP_OFF_WIN2_ENABLE,
    CLIP_OFF_WIN1_INSIDE, CLIP_OFF_WIN2_INSIDE,
    PPU_OFF_FIXED_COLOR_R, PPU_OFF_FIXED_COLOR_G, PPU_OFF_FIXED_COLOR_B,
    PPU_OFF_HDMA_BYTE, PPU_OFF_HDMA_ENDED,
    PPU_OFF_HBEAM_LATCH, PPU_OFF_GUN_V_LATCH,
    SNES_PPU_SIZE,
    CPU_OFF_V_COUNTER,
)


def _sync_ppu_postload_runtime(
    ppu_chunk: bytes,
    f01: bytes | None,
    cpu_chunk: bytes | None = None,
) -> bytes:
    """Restore PPU runtime flags that are not serialized by SR16's P01 table.

    snes9x stores a few derived/runtime PPU fields in snapshots. SR16's table
    does not have them, so the remapper leaves them zero. That is usually fine,
    but HDMA-heavy scenes can rely on window/color-math state before any new
    $2126-$2131 write changes a register and forces snes9x to rebuild clipping
    data. Mark it dirty up front when the saved hardware state says those
    features are active.
    """
    if f01 is None or len(f01) <= HDMAEN or len(ppu_chunk) < SNES_PPU_SIZE - 4:
        return ppu_chunk

    out = bytearray(ppu_chunk)
    hdma_enable = f01[HDMAEN]
    v_counter = (
        int.from_bytes(cpu_chunk[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4], "big")
        if cpu_chunk is not None and len(cpu_chunk) >= CPU_OFF_V_COUNTER + 4
        else 0
    )

    if hdma_enable and v_counter == 0:
        out[PPU_OFF_HDMA_BYTE] = hdma_enable
        out[PPU_OFF_HDMA_ENDED] = 0

    out[PPU_OFF_WIN1_LEFT]  = f01[WH0]
    out[PPU_OFF_WIN1_RIGHT] = f01[WH1]
    out[PPU_OFF_WIN2_LEFT]  = f01[WH2]
    out[PPU_OFF_WIN2_RIGHT] = f01[WH3]

    if len(out) >= PPU_OFF_CGDATA + CGRAM_BYTES:
        cgadd = out[PPU_OFF_CGADD]
        saved_index = ((cgadd - 1) & 0xFF) if cgadd else cgadd
        out[PPU_OFF_CG_SAVED_BYTE] = out[PPU_OFF_CGDATA + saved_index * 2 + 1]

    if len(out) >= PPU_OFF_GUN_V_LATCH + 2:
        h_latch = int.from_bytes(
            out[PPU_OFF_HBEAM_LATCH:PPU_OFF_HBEAM_LATCH + 2], "big"
        )
        if h_latch:
            # SR16's older timing reports the HV latch three dots earlier than
            # the snes9x core used by the target snapshots.
            out[PPU_OFF_HBEAM_LATCH:PPU_OFF_HBEAM_LATCH + 2] = (
                min(0x1FF, h_latch + 3).to_bytes(2, "big")
            )
        if out[PPU_OFF_GUN_V_LATCH:PPU_OFF_GUN_V_LATCH + 2] == b"\x00\x00":
            out[PPU_OFF_GUN_V_LATCH:PPU_OFF_GUN_V_LATCH + 2] = (1000).to_bytes(2, "big")

    window_or_color_math_live = any(
        f01[addr] for addr in (
            W12SEL, W34SEL, WOBJSEL,
            WBGLOG, WOBJLOG,
            0x2130, 0x2131, COLDATA,
        )
    )
    hdma_touches_window_or_color_math = False
    if len(f01) >= DMA_REGS_END:
        for ch in range(8):
            if not (hdma_enable & (1 << ch)):
                continue
            b_addr = f01[DMA_REGS_BASE + ch * DMA_CH_STRIDE + DMA_OFF_BBAD]
            # 0x23..0x32 = the window/color-math PPU registers' B-bus low bytes
            if 0x23 <= b_addr <= 0x32:
                hdma_touches_window_or_color_math = True
                break

    if window_or_color_math_live or hdma_touches_window_or_color_math:
        # Rebuild the PPU-side window fields from the canonical hardware
        # mirrors. Snapshot loading copies FillRAM directly and does not replay
        # S9xSetPPU(), so these derived fields can otherwise be stale on the
        # first rendered frame.
        w12sel = f01[W12SEL]
        w34sel = f01[W34SEL]
        wobjsel = f01[WOBJSEL]
        # (selector_byte, low_slot_idx, high_slot_idx)
        # Slot order: BG1 BG2 BG3 BG4 OBJ Color  (6 slots, 6B each)
        selectors = ((w12sel, 0, 1), (w34sel, 2, 3), (wobjsel, 4, 5))
        for byte, low_idx, high_idx in selectors:
            low = PPU_OFF_CLIP_BLOCK + low_idx * PPU_CLIP_SLOT_STRIDE
            high = PPU_OFF_CLIP_BLOCK + high_idx * PPU_CLIP_SLOT_STRIDE
            out[low + CLIP_OFF_WIN1_ENABLE]  = 1 if (byte & 0x02) else 0
            out[high + CLIP_OFF_WIN1_ENABLE] = 1 if (byte & 0x20) else 0
            out[low + CLIP_OFF_WIN2_ENABLE]  = 1 if (byte & 0x08) else 0
            out[high + CLIP_OFF_WIN2_ENABLE] = 1 if (byte & 0x80) else 0
            out[low + CLIP_OFF_WIN1_INSIDE]  = 0 if (byte & 0x01) else 1
            out[high + CLIP_OFF_WIN1_INSIDE] = 0 if (byte & 0x10) else 1
            out[low + CLIP_OFF_WIN2_INSIDE]  = 0 if (byte & 0x04) else 1
            out[high + CLIP_OFF_WIN2_INSIDE] = 0 if (byte & 0x40) else 1

        wbglog = f01[WBGLOG]
        wobjlog = f01[WOBJLOG]
        # 6-byte clip slot: byte 0 = ClipCounts, byte 1 = ClipWindowOverlapLogic.
        # We're writing the per-slot Logic byte for BG1..4 (slots 0..3) + OBJ/Color.
        out[PPU_OFF_CLIP_BLOCK + 0 * PPU_CLIP_SLOT_STRIDE + 1] = wbglog & 0x03
        out[PPU_OFF_CLIP_BLOCK + 1 * PPU_CLIP_SLOT_STRIDE + 1] = (wbglog >> 2) & 0x03
        out[PPU_OFF_CLIP_BLOCK + 2 * PPU_CLIP_SLOT_STRIDE + 1] = (wbglog >> 4) & 0x03
        out[PPU_OFF_CLIP_BLOCK + 3 * PPU_CLIP_SLOT_STRIDE + 1] = (wbglog >> 6) & 0x03
        out[PPU_OFF_CLIP_BLOCK + 4 * PPU_CLIP_SLOT_STRIDE + 1] = wobjlog & 0x03
        out[PPU_OFF_CLIP_BLOCK + 5 * PPU_CLIP_SLOT_STRIDE + 1] = (wobjlog >> 2) & 0x03

        coldata = f01[COLDATA]
        if coldata & 0x20:
            out[PPU_OFF_FIXED_COLOR_R] = coldata & 0x1F
        if coldata & 0x40:
            out[PPU_OFF_FIXED_COLOR_G] = coldata & 0x1F
        if coldata & 0x80:
            out[PPU_OFF_FIXED_COLOR_B] = coldata & 0x1F

        out[PPU_OFF_RECOMPUTE_CLIP] = 1
    else:
        out[PPU_OFF_RECOMPUTE_CLIP] = 0

    return bytes(out)


# Fields that are documented as missing in SR16's FreezeData table. They get
# zero-filled in the snes9x output by design — do not warn about these.
# CGSavedByte is reconstructed by _sync_ppu_postload_runtime below, so the
# remapper's zero-fill is harmless even though it appears "missing".
_KNOWN_MISSING_PPU_FIELDS = frozenset((
    "GunHLatch", "GunVLatch",
    "HDMA", "HDMAEnded",
    "VRAMReadBuffer",
    "CGSavedByte",
))

_log = logging.getLogger("converter.sr16_to_snes9x.state.ppu")


def _extract_ppu(p01: bytes) -> bytes:
    """Extract snes9x v12 PPU chunk (2652B) from SR16 P01 (2645B).

    SR16 and snes9x serialize PPU fields in different orders. The remapper
    walks the snes9x SnapPPU layout and copies each field by name from the
    SR16 P01 data. See ``converter/sr16_to_snes9x/state/ppu_remap.py`` for the layout
    definitions.

    Logs DEBUG for every missing field; logs WARNING (and emits via
    ``warnings.warn``) for any missing field that is not in the known-missing
    allowlist — that signals a freezedata.json drift or new snes9x layout.
    """
    from .ppu_remap import remap_p01_to_ppu
    out, missing = remap_p01_to_ppu(p01)
    if missing:
        unexpected = [n for n in missing if n not in _KNOWN_MISSING_PPU_FIELDS]
        for name in missing:
            _log.debug("PPU field missing in SR16, zero-filled: %s", name)
        if unexpected:
            import warnings
            warnings.warn(
                "PPU remap missing unexpected field(s) (output will be "
                f"zero-filled): {', '.join(unexpected)}",
                stacklevel=2,
            )
    return out
