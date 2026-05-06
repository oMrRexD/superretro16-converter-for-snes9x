"""Reconstruct SR16 F01 FillRAM from snes9x FIL + DMA chunks.

snes9x's FIL stores FillRAM with the open-bus pattern (0x43) in the DMA
register page ($4300-$437F). SR16 reads actual DMA configuration from these
registers, so we must reconstruct them from the snes9x DMA chunk.

The function deliberately leaves the PPU register mirror intact. Those bytes
carry the game's current color-math/window state, while the DMA register page
is reconstructed from structured DMA state below.
"""
from __future__ import annotations

from converter.common.constants import (
    SNES_DMA_SIZE, SNES_DMA_CHANNELS, SNES_DMA_CHANNEL_SIZE,
    DMA_REGS_BASE, DMA_CH_STRIDE, DMA_REGS_END,
    DMA_OFF_DMAP, DMA_OFF_BBAD,
    DMA_OFF_A1TL, DMA_OFF_A1TH, DMA_OFF_A1B,
    DMA_OFF_DASL, DMA_OFF_DASH, DMA_OFF_DASB,
)


def reconstruct_f01(fil: bytes, dma: bytes) -> bytes:
    """Build SR16-compatible F01 from snes9x FIL + DMA chunks.

    Reconstructs $4300-$437F DMA registers from the snes9x DMA chunk's
    per-channel boolean fields, since snes9x's FIL leaves these as
    open-bus (0x43) garbage.

    snes9x SnapDMA per channel (19 bytes):
      [0]  ReverseTransfer   → bit 7 of DMAPx
      [1]  HDMAIndirect      → bit 6
      [2]  UnusedBit43x0     → bit 5
      [3]  AAddressFixed     → bit 3
      [4]  AAddressDecrement → bit 4
      [5]  TransferMode      → bits 0-2
      [6]  BAddress          → $43x1
      [7:9]  AAddress        -> $43x2-$43x3 (2B BE -> LE pair)
      [9]  ABank             → $43x4
      [10:12] DMACount       -> $43x5-$43x6 (2B BE -> LE pair)
      [12] IndirectBank       → $43x7
      [13:15] Address        -> $43x8-$43x9 (2B BE -> LE pair)
      [15] Repeat            → (not a register — runtime state)
      [16] LineCount          → $43xA (HDMA line counter)
      [17] UnknownByte        → (not a register)
      [18] DoTransfer         → (not a register — runtime state)
    """
    out = bytearray(fil)

    if len(dma) < SNES_DMA_SIZE or len(out) < DMA_REGS_END:
        return bytes(out)

    # --- Fix 1: Reconstruct DMA registers ($4300-$437F) ---
    for ch in range(SNES_DMA_CHANNELS):
        si = ch * SNES_DMA_CHANNEL_SIZE
        ri = DMA_REGS_BASE + ch * DMA_CH_STRIDE  # FillRAM register base

        # Reconstruct DMAPx ($43x0) from individual bool fields
        rt    = dma[si + 0]   # ReverseTransfer
        hdmai = dma[si + 1]   # HDMAIndirectAddressing
        ub43  = dma[si + 2]   # UnusedBit43x0
        aaf   = dma[si + 3]   # AAddressFixed
        aad   = dma[si + 4]   # AAddressDecrement
        tm    = dma[si + 5]   # TransferMode
        dmap = (
            ((rt & 1) << 7) |
            ((hdmai & 1) << 6) |
            ((ub43 & 1) << 5) |
            ((aad & 1) << 4) |
            ((aaf & 1) << 3) |
            (tm & 0x07)
        )
        out[ri + DMA_OFF_DMAP] = dmap

        # BAddress ($43x1)
        out[ri + DMA_OFF_BBAD] = dma[si + 6]

        # AAddress ($43x2-$43x3): snes9x stores as 2B BE, SNES registers are LE
        out[ri + DMA_OFF_A1TL] = dma[si + 8]   # low byte (BE[1])
        out[ri + DMA_OFF_A1TH] = dma[si + 7]   # high byte (BE[0])

        # ABank ($43x4)
        out[ri + DMA_OFF_A1B] = dma[si + 9]

        # DMACount / HDMA indirect address ($43x5-$43x6): 2B BE -> LE
        out[ri + DMA_OFF_DASL] = dma[si + 11]  # low byte
        out[ri + DMA_OFF_DASH] = dma[si + 10]  # high byte

        # IndirectBank ($43x7)
        out[ri + DMA_OFF_DASB] = dma[si + 12]

        # HDMA table address ($43x8-$43x9): from Address field 2B BE -> LE
        out[ri + 0x08] = dma[si + 14]  # low byte
        out[ri + 0x09] = dma[si + 13]  # high byte

        # HDMA line counter ($43xA)
        out[ri + 0x0A] = dma[si + 16]  # LineCount

        # Unused regs $43xB-$43xF: leave as-is (snes9x open-bus or zero)
        for off in range(0x0B, 0x10):
            out[ri + off] = 0x43

    # Note: PPU registers like CGWSEL ($2130) and CGADSUB ($2131) in FillRAM
    # are the game's actual color math configuration, NOT HDMA-transient values.
    # They must be preserved as-is from the snes9x FIL. Zeroing them would
    # disable color math, hiding any content rendered on the sub screen
    # (e.g. Super Metroid's HUD which is on TS/BG3).

    return bytes(out)
