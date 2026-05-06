"""snes9x DMA(152B) → SR16 D01(152B) — reverse field reorder.

Reverse of ``converter.sr16_to_snes9x.state.dma._extract_dma``.
"""
from __future__ import annotations

from converter.common.constants import (
    SNES_DMA_SIZE, SR16_D01_SIZE,
    SNES_DMA_CHANNELS, SNES_DMA_CHANNEL_SIZE,
)


def build_d01(dma: bytes) -> bytes:
    """Remap snes9x SnapDMA field order to SR16 D01 field order.

    snes9x SnapDMA per channel (19B):
      [0]  ReverseTransfer
      [1]  HDMAIndirectAddressing
      [2]  UnusedBit43x0
      [3]  AAddressFixed
      [4]  AAddressDecrement
      [5]  TransferMode
      [6]  BAddress
      [7:9]  AAddress (2B BE)
      [9]  ABank
      [10:12] DMACount (2B BE)
      [12] IndirectBank
      [13:15] Address (2B BE)
      [15] Repeat
      [16] LineCount
      [17] UnknownByte
      [18] DoTransfer

    SR16 D01 per channel (19B):
      [0]  ReverseTransfer
      [1]  AAddressDecrement       was at snes9x[4]
      [2]  UnusedBit43x0
      [3]  TransferMode           was at snes9x[5]
      [4]  ABank                  was at snes9x[9]
      [5:7]  AAddress             was at snes9x[7:9]
      [7:9]  Address              was at snes9x[13:15]
      [9]  BAddress               was at snes9x[6]
      [10] HDMAIndirectAddressing was at snes9x[1]
      [11:13] DMACount            was at snes9x[10:12]
      [13] IndirectBank           was at snes9x[12]
      [14] Repeat                 was at snes9x[15]
      [15] LineCount              was at snes9x[16]
      [16] AAddressFixed          was at snes9x[3]
      [17] UnknownByte            was at snes9x[17]
      [18] reset-channel sentinel / SR16 runtime DoTransfer
    """
    if len(dma) != SNES_DMA_SIZE:
        raise ValueError(f"DMA chunk size {len(dma)} != {SNES_DMA_SIZE}")

    out = bytearray(SR16_D01_SIZE)
    for ch in range(SNES_DMA_CHANNELS):
        si = ch * SNES_DMA_CHANNEL_SIZE
        oi = ch * SNES_DMA_CHANNEL_SIZE

        # Read snes9x fields
        RT   = dma[si + 0]
        HDMAI = dma[si + 1]
        UB43 = dma[si + 2]
        AAF  = dma[si + 3]   # AAddressFixed
        AAD  = dma[si + 4]   # AAddressDecrement
        TM   = dma[si + 5]   # TransferMode
        BA   = dma[si + 6]   # BAddress
        AAdr = dma[si + 7:si + 9]  # AAddress (2B BE)
        AB   = dma[si + 9]   # ABank
        DC   = dma[si + 10:si + 12]  # DMACount (2B BE)
        IB   = dma[si + 12]  # IndirectBank
        Addr = dma[si + 13:si + 15]  # Address (2B BE)
        Re   = dma[si + 15]  # Repeat
        LC   = dma[si + 16]  # LineCount
        UB   = dma[si + 17]  # UnknownByte
        DT   = dma[si + 18]  # DoTransfer

        # Write in SR16 D01 order.  SR16's old DMA struct does not serialize
        # the first few booleans in the same order as SnapDMA.  Native SR16
        # saves show AAddressDecrement at byte 1 and HDMAIndirectAddressing at
        # byte 10.  Byte 18 is zero for live/configured channels; the value 1
        # is part of the reset-channel pattern, not SnapDMA's active HDMA flag.
        out[oi + 0]  = RT
        out[oi + 1]  = AAD
        out[oi + 2]  = UB43
        out[oi + 3]  = TM      # TransferMode
        out[oi + 4]  = AB      # ABank
        out[oi + 5:oi + 7] = AAdr  # AAddress
        out[oi + 7:oi + 9] = Addr  # Address
        out[oi + 9]  = BA      # BAddress
        out[oi + 10] = HDMAI   # HDMAIndirectAddressing
        out[oi + 11:oi + 13] = DC  # DMACount
        out[oi + 13] = IB      # IndirectBank
        out[oi + 14] = Re      # Repeat
        out[oi + 15] = LC      # LineCount
        out[oi + 16] = AAF     # AAddressFixed
        out[oi + 17] = UB      # UnknownByte
        out[oi + 18] = 0

    return bytes(out)
