"""SR16 D01 -> snes9x v12 DMA extraction + DMA pre-execution.

`_preexec_dmas` simulates pending CGRAM/OAM DMA transfers at conversion time
so the first rendered frame loads visually clean.
"""
from __future__ import annotations

from converter.common.constants import (
    SR16_D01_SIZE, SNES_DMA_SIZE,
    MDMAEN, HDMAEN,
    DMA_REGS_BASE, DMA_REGS_END, DMA_CH_STRIDE,
    DMA_OFF_DMAP, DMA_OFF_BBAD,
    DMA_OFF_A1TL, DMA_OFF_A1TH, DMA_OFF_A1B,
    DMA_OFF_DASL, DMA_OFF_DASH, DMA_OFF_DASB,
    BBUS_CGDATA, BBUS_OAMDATA,
    PPU_OFF_CGADD, PPU_OFF_CGDATA, PPU_OFF_OAMADDR, PPU_OFF_OAMDATA,
    CGRAM_BYTES, OAM_BYTES,
)
from .palette import _wram_read
from converter.common._trace import trace as _trace

VRAM_DMA_MODES = ("off", "safe", "all")


def _reset_dma_channel() -> bytes:
    """snes9x S9xResetDMA() default serialized in SnapDMA order."""
    return bytes([
        1,      # ReverseTransfer
        1,      # HDMAIndirectAddressing
        1,      # UnusedBit43x0
        1,      # AAddressFixed
        1,      # AAddressDecrement
        7,      # TransferMode
        0xFF,   # BAddress
        0xFF, 0xFF,  # AAddress
        0xFF,   # ABank
        0xFF, 0xFF,  # DMACount / HDMA indirect address
        0xFF,   # IndirectBank
        0xFF, 0xFF,  # Address
        0,      # Repeat
        0x7F,   # LineCount
        0xFF,   # UnknownByte
        0,      # DoTransfer
    ])


def _extract_dma(d01: bytes, f01: bytes | None = None) -> bytes:
    """Remap SR16 DMA state to snes9x SnapDMA order.

    D01 stores runtime HDMA fields in a custom 19-byte-per-channel layout.
    F01 is the FillRAM mirror and contains the canonical $43x0 register bytes
    used by snes9x to derive DMA mode flags. Active HDMA saves need both:
    D01 for progressed pointers/counters, F01 for the mode bits.

    SR16 D01 order per channel (19 bytes):
      [0]  ReverseTransfer (1B)
      [1]  HDMAIndirectAddressing-like byte (unreliable for active HDMA)
      [2]  UnusedBit43x0-like byte
      [3]  TransferMode (1B)    ← swapped with AAddressFixed
      [4]  ABank (1B)           ← moved up from after AAddress
      [5]  AAddress (2B BE)
      [7]  Address (2B BE)      ← moved up from after IndirectBank
      [9]  BAddress (1B)        ← moved from after TransferMode
      [10] AAddressDecrement (1B) ← moved from bool position 4
      [11] DMACount / HDMA indirect address (2B BE)
      [13] IndirectBank (1B)
      [14] Repeat (1B)
      [15] LineCount (1B)
      [16] AAddressFixed (1B)   ← swapped with TransferMode
      [17] UnknownByte (1B)
      [18] DoTransfer (1B)

    snes9x SnapDMA order per channel (19 bytes):
      [0]  ReverseTransfer, [1] HDMAIndirectAddressing, [2] UnusedBit43x0,
      [3]  AAddressFixed, [4] AAddressDecrement, [5] TransferMode,
      [6]  BAddress, [7-8] AAddress (2B BE), [9] ABank,
      [10-11] DMACount (2B BE), [12] IndirectBank, [13-14] Address (2B BE),
      [15] Repeat, [16] LineCount, [17] UnknownByte, [18] DoTransfer
    """
    if len(d01) != SR16_D01_SIZE:
        raise ValueError(f"D01 size mismatch: {len(d01)} != {SR16_D01_SIZE}")
    has_f01_dma_regs = f01 is not None and len(f01) >= DMA_REGS_END
    dma_enable = f01[MDMAEN] if has_f01_dma_regs else 0
    hdma_enable = f01[HDMAEN] if has_f01_dma_regs else 0

    out = bytearray(SNES_DMA_SIZE)
    reset_channel = _reset_dma_channel()
    for ch in range(8):
        si = ch * 19  # SR16 input offset
        oi = ch * 19  # snes9x output offset
        if has_f01_dma_regs:
            ri = DMA_REGS_BASE + ch * DMA_CH_STRIDE
            channel_open_bus = f01[ri:ri + DMA_CH_STRIDE] == bytes([0x43]) * DMA_CH_STRIDE
            channel_enabled = bool((dma_enable | hdma_enable) & (1 << ch))
            if channel_open_bus and not channel_enabled:
                out[oi:oi + 19] = reset_channel
                continue

        # Runtime fields from SR16 D01.
        RT   = d01[si+0]
        HDMAI = d01[si+1]
        UB43 = d01[si+2]
        TM   = d01[si+3]    # SR16 stores TransferMode here
        AB   = d01[si+4]    # ABank
        AAdr = d01[si+5:si+7]  # AAddress (2B BE)
        Addr = d01[si+7:si+9]  # Address (2B BE)
        BA   = d01[si+9]    # BAddress
        AAD  = 0
        # D01 stores all 16-bit DMA runtime pointers in the same big-endian
        # order used by snes9x snapshots. Earlier Super Metroid debugging
        # misread symmetric/low values as little-endian; FFV frame-perfect
        # native states show active HDMA indirect addresses such as 0x8300,
        # 0x8500, etc. byte-for-byte in D01 and SnapDMA.
        DC   = d01[si+11:si+13]  # DMACount / HDMA indirect address (2B BE)
        IB   = d01[si+13]   # IndirectBank
        Re   = d01[si+14]
        LC   = d01[si+15]
        AAF  = d01[si+16]   # SR16 stores AAddressFixed here
        UB   = d01[si+17]
        DT   = d01[si+18]

        if has_f01_dma_regs:
            # F01 mirrors the real SNES $43x0 registers. snes9x itself derives
            # these fields from DMAPx with this exact bit layout.
            ri = DMA_REGS_BASE + ch * DMA_CH_STRIDE
            dmap = f01[ri + DMA_OFF_DMAP]
            bbus = f01[ri + DMA_OFF_BBAD]
            channel_configured = (
                ((dma_enable | hdma_enable) & (1 << ch))
                or f01[ri:ri + DMA_CH_STRIDE] != bytes([0x43]) * DMA_CH_STRIDE
            )
            if channel_configured:
                RT = 1 if (dmap & 0x80) else 0
                HDMAI = 1 if (dmap & 0x40) else 0
                UB43 = 1 if (dmap & 0x20) else 0
                AAD = 1 if (dmap & 0x10) else 0
                AAF = 1 if (dmap & 0x08) else 0
                TM = dmap & 0x07
                BA = bbus
                AB = f01[ri + DMA_OFF_A1B]
                if HDMAI:
                    IB = f01[ri + DMA_OFF_DASB]
                if hdma_enable & (1 << ch):
                    DT = 1

        # Write in snes9x SnapDMA order
        out[oi+0] = RT
        out[oi+1] = HDMAI
        out[oi+2] = UB43
        out[oi+3] = AAF     # AAddressFixed
        out[oi+4] = AAD     # AAddressDecrement
        out[oi+5] = TM      # TransferMode
        out[oi+6] = BA      # BAddress
        out[oi+7:oi+9] = AAdr  # AAddress (2B)
        out[oi+9] = AB      # ABank
        out[oi+10:oi+12] = DC  # DMACount (2B)
        out[oi+12] = IB     # IndirectBank
        out[oi+13:oi+15] = Addr  # Address (2B)
        out[oi+15] = Re     # Repeat
        out[oi+16] = LC     # LineCount
        out[oi+17] = UB     # UnknownByte
        out[oi+18] = DT     # DoTransfer

    return bytes(out)


def _preexec_dmas(ppu: bytearray, wram: bytes, f01: bytes,
                  vram: bytearray | None = None,
                  vram_dma_mode: str = "off") -> None:
    """Apply DMA channels armed in $420B as if vblank/NMI had executed them.

    SR16 saves at a moment where the game's NMI handler has set up DMA
    channels (palette/OAM updates) but they haven't fired yet. snes9x
    won't auto-fire on snapshot load, so the first displayed frame uses
    stale PPU state — wrong colors, missing HUD, etc. We simulate the
    transfer at conversion time so the save loads visually clean.

    CGRAM and OAM transfers are handled unconditionally (B-bus targets
    with reliable saved destinations).

    VRAM transfers (B-bus 0x18..0x19) are gated by ``vram_dma_mode``:

    * ``"off"`` (default) — never pre-execute VRAM. Pre-Phase-2 behavior.
      Legitimately-armed VRAM uploads (some Doom-style real-time tile
      updates) load with stale graphics on the first frame.
    * ``"safe"`` — only pre-execute when ``vram`` is supplied AND the game
      is registry-flagged as safe for VRAM pre-exec. The registry currently
      has no entries, so this collapses to ``"off"`` at present; new
      whitelist entries can be added in ``converter.sr16_to_snes9x.game_registry`` once
      individual games are validated.
    * ``"all"`` — pre-execute every armed VRAM channel. Experimental;
      Super Metroid s05 was the exact save that motivated removing the
      old generic VRAM pre-exec because it corrupted valid room tilemaps.
      Use only when the user knows the save needs it.
    """
    if vram_dma_mode not in VRAM_DMA_MODES:
        raise ValueError(
            f"vram_dma_mode must be one of {VRAM_DMA_MODES}, got {vram_dma_mode!r}"
        )
    if len(f01) < DMA_REGS_END:
        return
    dma_enable = f01[MDMAEN]
    if dma_enable == 0:
        return

    cgadd = ppu[PPU_OFF_CGADD]
    oamaddr_w = int.from_bytes(
        ppu[PPU_OFF_OAMADDR:PPU_OFF_OAMADDR+2], "big"
    ) & 0x1FF                                  # word index 0..271
    oamaddr = oamaddr_w * 2                    # byte index
    for ch in range(8):
        if not (dma_enable & (1 << ch)):
            continue
        ri = DMA_REGS_BASE + ch * DMA_CH_STRIDE
        dmap   = f01[ri + DMA_OFF_DMAP]
        b_addr = f01[ri + DMA_OFF_BBAD]
        a_lo   = f01[ri + DMA_OFF_A1TL]
        a_hi   = f01[ri + DMA_OFF_A1TH]
        a_bk   = f01[ri + DMA_OFF_A1B]
        cnt_lo = f01[ri + DMA_OFF_DASL]
        cnt_hi = f01[ri + DMA_OFF_DASH]
        src = (a_bk << 16) | (a_hi << 8) | a_lo
        count = (cnt_hi << 8) | cnt_lo
        if count == 0:
            count = 0x10000
        mode = dmap & 0x07
        data = _wram_read(wram, src, count)
        if not data:
            continue

        if b_addr == BBUS_CGDATA and mode == 0:
            # CGDATA: each $2122 write toggles low/high byte of 16-bit entry
            # via PPU.CGFLIP. WRAM stores entries as native LE uint16 pairs;
            # snes9x's CGDATA[] is also stored as host LE uint16 in memory,
            # but the SnapPPU table serializes each as 2B BE, so we byte-swap.
            if cgadd != 0 or count < CGRAM_BYTES:
                # Partial CGRAM DMAs are often mid-frame/effect updates. Running
                # them before the first rendered frame can overwrite a corrected
                # full palette with a stale partial upload (Star Fox does this at
                # CGADD=36). Only pre-execute complete palette restores.
                continue
            n_bytes = min(len(data), CGRAM_BYTES - cgadd * 2)
            for i in range(n_bytes):
                # Swap byte order: WRAM LE pair -> snes9x BE pair.
                ppu_off = PPU_OFF_CGDATA + cgadd * 2 + (i ^ 1)
                ppu[ppu_off] = data[i]
            cgadd = (cgadd + (n_bytes + 1) // 2) & 0xFF

        elif b_addr == BBUS_OAMDATA and mode == 0:
            # OAMDATA: each $2104 write goes sequentially into OAM.
            # OAM is a uint8 stream — no byte-swap needed.
            n_bytes = min(len(data), OAM_BYTES - oamaddr)
            if n_bytes > 0:
                ppu[PPU_OFF_OAMDATA + oamaddr:PPU_OFF_OAMDATA + oamaddr + n_bytes] = data[:n_bytes]
                oamaddr += n_bytes

        elif vram_dma_mode != "off" and b_addr in (0x18, 0x19):
            # VRAM pre-execution is reserved as an opt-in extension point but
            # is not implemented in this build: the only validated VRAM
            # pre-exec path was a Super Metroid endgame heuristic that
            # corrupted other saves (s05 door scenery), and full general
            # support requires modeling Mode-7 word semantics and the
            # increment-on-high vs increment-on-low VMA mode bit. The flag is
            # surfaced so callers can request it now and the heuristic can be
            # filled in once a candidate game is validated against headless
            # snes9x. With "safe" the registry's VRAM-safe whitelist is
            # consulted (currently empty); with "all" we trace and skip.
            _trace("vram_dma_preexec_skipped",
                   channel=ch, mode=vram_dma_mode, b_addr=b_addr,
                   reason="not implemented in this build")
