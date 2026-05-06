"""SR16 C01 -> snes9x v12 CPU/REG/TIM extraction + IRQ/HDMA scheduler sync.

C01 packs 161 bytes using SR16's FreezeData table, not a native snes9x
CPU/REG/TIM dump. The fields we trust are decoded by the explicit offsets in
``converter.common.constants``:
  +0x00..+0x1D   65816 registers (DB/P/A/D/S/X/Y/PB:PC)
  +0x21..+0x58   selected CPU scheduler fields
  +0x72..+0x86   selected timing fields
  remaining bytes are legacy/runtime fields that are not copied blindly

snes9x v12 expects three separate chunks: CPU (48B), REG (16B), TIM (70B).
``_extract_cpu`` is a thin orchestrator — the real work lives in three
single-responsibility helpers (``_build_reg_chunk``, ``_build_cpu_chunk``,
``_build_tim_chunk``).
"""
from __future__ import annotations

from converter.common.constants import (
    NMITIMEN, HTIMEL, HTIMEH, VTIMEL, VTIMEH, MDMAEN, HDMAEN,
    SNES_CPU_SIZE, SNES_REG_SIZE, SNES_TIM_SIZE,
    CPU_OFF_CYCLES, CPU_OFF_V_COUNTER,
    CPU_OFF_FAST_ROM_SPEED,
    CPU_OFF_WHICH_EVENT, CPU_OFF_NEXT_EVENT,
    CPU_OFF_WAITING_FOR_INTERRUPT, CPU_OFF_NMI_PENDING,
    HC_HDMA_INIT_EVENT, HC_RENDER_EVENT,
    TIM_OFF_H_MAX_MASTER, TIM_OFF_H_MAX, TIM_OFF_V_MAX,
    TIM_OFF_WRAM_REFRESH, TIM_OFF_INTERLACE,
    TIM_OFF_IRQ_TRIGGER, TIM_OFF_NEXT_IRQ,
    NO_IRQ_PENDING, NO_IRQ_PENDING_INIT,
    PPU_OFF_HTIMER_ENABLED, PPU_OFF_VTIMER_ENABLED,
    PPU_OFF_HTIMER_POS, PPU_OFF_VTIMER_POS,
    PPU_OFF_IRQ_H_BEAM, PPU_OFF_IRQ_V_BEAM,
    SR16_REG_OFF_DB, SR16_REG_OFF_P, SR16_REG_OFF_A, SR16_REG_OFF_D,
    SR16_REG_OFF_S, SR16_REG_OFF_X, SR16_REG_OFF_Y, SR16_REG_OFF_PC_FULL,
    C01_OFF_CYCLES, C01_OFF_WAITING_FOR_INTERRUPT,
    C01_OFF_WHICH_EVENT, C01_OFF_NEXT_EVENT,
    C01_OFF_V_COUNTER, C01_OFF_FAST_ROM_SPEED,
    C01_OFF_TIMINGS_H_MAX, C01_OFF_TIMINGS_V_MAX_M,
    C01_OFF_TIMINGS_V_MAX, C01_OFF_TIMINGS_NMI,
    C01_OFF_TIMINGS_WRAM_REF, C01_OFF_INTERLACE,
)


_OLD_EVENT_TO_V12 = {
    12: 1, 1: 1,
    2: 2, 3: 2,
    4: 3, 5: 3,
    6: 4, 7: 4,
    8: 5, 9: 5,
    10: 6, 11: 6,
}


def _be_u(buf: bytes, off: int, size: int) -> int:
    """Read unsigned big-endian int from buffer."""
    return int.from_bytes(buf[off:off + size], "big")


# ---------------------------------------------------------------------------
# Per-chunk builders
# ---------------------------------------------------------------------------

def _build_reg_chunk(c01: bytes) -> bytes:
    """Build snes9x REG chunk (16B): PB(1) DB(1) P A D S X Y PC, all 2B BE."""
    db = _be_u(c01, SR16_REG_OFF_DB, 1)
    p  = _be_u(c01, SR16_REG_OFF_P, 4) & 0xFFFF   # P.W = low 16 bits
    a  = _be_u(c01, SR16_REG_OFF_A, 4) & 0xFFFF
    d  = _be_u(c01, SR16_REG_OFF_D, 4) & 0xFFFF
    s  = _be_u(c01, SR16_REG_OFF_S, 4) & 0xFFFF
    x  = _be_u(c01, SR16_REG_OFF_X, 4) & 0xFFFF
    y  = _be_u(c01, SR16_REG_OFF_Y, 4) & 0xFFFF
    pc_full = _be_u(c01, SR16_REG_OFF_PC_FULL, 4)  # high byte = PB, low 16 = PC
    pb = (pc_full >> 16) & 0xFF
    pc = pc_full & 0xFFFF

    out = bytearray(SNES_REG_SIZE)
    out[0]      = pb
    out[1]      = db
    out[2:4]    = p.to_bytes(2, "big")
    out[4:6]    = a.to_bytes(2, "big")
    out[6:8]    = d.to_bytes(2, "big")
    out[8:10]   = s.to_bytes(2, "big")
    out[10:12]  = x.to_bytes(2, "big")
    out[12:14]  = y.to_bytes(2, "big")
    out[14:16]  = pc.to_bytes(2, "big")
    return bytes(out)


def _build_cpu_chunk(c01: bytes) -> bytes:
    """Build snes9x CPU chunk (48B) from SR16 C01 with safe NTSC defaults.

    Only Cycles and V_Counter are taken from SR16; the rest are deliberate
    defaults because SR16's serialized scheduler/event state is incompatible
    with snes9x's. Layout (snes9x.h SCPUState + snapshot.cpp SnapCPU[]):
      Cycles(4) PrevCycles(4) V_Counter(4) Flags(4)
      IRQPending(4) MemSpeed(4) MemSpeedx2(4) FastROMSpeed(4)
      InDMA(1) InHDMA(1) InDMAorHDMA(1) InWRAMDMAorHDMA(1)
      HDMARanInDMA(1) WhichEvent(1) NextEvent(4)
      WaitingForInterrupt(1)
      NMIPending(1) IRQLine(1) IRQTransition(1) IRQLastState(1) IRQExternal(1)
    """
    sr_cycles = _be_u(c01, C01_OFF_CYCLES, 4)
    sr_v_counter = _be_u(c01, C01_OFF_V_COUNTER, 4)
    sr_fast_rom = _be_u(c01, C01_OFF_FAST_ROM_SPEED, 4)
    sr_which_event = c01[C01_OFF_WHICH_EVENT]
    sr_next_event = _be_u(c01, C01_OFF_NEXT_EVENT, 4)
    waiting_for_interrupt = c01[C01_OFF_WAITING_FOR_INTERRUPT]

    out = bytearray()
    out += sr_cycles.to_bytes(4, "big")
    out += (182).to_bytes(4, "big")     # PrevCycles
    out += sr_v_counter.to_bytes(4, "big")
    out += (0x10).to_bytes(4, "big")    # Flags (SCAN_KEYS_FLAG)
    out += (0).to_bytes(4, "big")       # IRQPending
    out += (8).to_bytes(4, "big")       # MemSpeed (SLOW_ONE_CYCLE)
    out += (16).to_bytes(4, "big")      # MemSpeedx2
    out += (sr_fast_rom or 8).to_bytes(4, "big")  # FastROMSpeed
    out += b"\x00" * 5                  # InDMA..HDMARanInDMA (5 bool8)
    out.append(_OLD_EVENT_TO_V12.get(sr_which_event, sr_which_event))
    out += sr_next_event.to_bytes(4, "big")
    out.append(1 if waiting_for_interrupt else 0)
    out += b"\x00" * 5                  # NMIPending..IRQExternal
    assert len(out) == SNES_CPU_SIZE, f"CPU chunk size {len(out)}"
    return bytes(out)


def _build_tim_chunk(c01: bytes) -> bytes:
    """Build snes9x TIM chunk (70B, mixed widths).

    Layout (snapshot.cpp SnapTimings[] + snes9x.h STimings):
      v6: H_Max_Master H_Max V_Max_Master V_Max
          HBlankStart HBlankEnd HDMAInit HDMAStart
          NMITriggerPos WRAMRefreshPos RenderPos
          InterlaceField (bool8 = 1 byte!)
          DMACPUSync NMIDMADelay IRQFlagChanging APUSpeedup
      v7: IRQTriggerCycles APUAllowTimeOverflow(bool8)
      v11: NextIRQTimer
    Total = 15*4 + 1 + 1*4 + 1 + 1*4 = 70 bytes.
    """
    h_max     = _be_u(c01, C01_OFF_TIMINGS_H_MAX, 4)
    v_max_m   = _be_u(c01, C01_OFF_TIMINGS_V_MAX_M, 4)
    v_max     = _be_u(c01, C01_OFF_TIMINGS_V_MAX, 4)
    nmi_pos   = _be_u(c01, C01_OFF_TIMINGS_NMI, 4)
    wram_ref  = _be_u(c01, C01_OFF_TIMINGS_WRAM_REF, 4)
    interlace = _be_u(c01, C01_OFF_INTERLACE, 1)

    out = bytearray()
    for v in [
        h_max, h_max, v_max_m, v_max,    # H_Max_Master..V_Max
        1096, 4, 20, 1106,                # HBlankStart..HDMAStart
        nmi_pos, wram_ref, 512,           # NMITriggerPos..RenderPos
    ]:
        out += v.to_bytes(4, "big")
    out.append(interlace)                # InterlaceField (bool8)
    for v in [18, 24, 0, 0]:             # DMACPUSync..APUSpeedup
        out += v.to_bytes(4, "big")
    out += (14).to_bytes(4, "big")       # IRQTriggerCycles (v7)
    out.append(0)                        # APUAllowTimeOverflow (v7 bool8)
    out += NO_IRQ_PENDING_INIT.to_bytes(4, "big")  # NextIRQTimer (v11)
    assert len(out) == SNES_TIM_SIZE, f"TIM chunk size {len(out)}"
    return bytes(out)


def _extract_cpu(c01: bytes) -> tuple[bytes, bytes, bytes]:
    """Return (CPU, REG, TIM) chunks built from SR16 C01 (161B).

    See ``_build_*_chunk`` helpers for per-chunk details. Kept as a single
    public entry to preserve the historical 3-tuple call site.
    """
    return _build_cpu_chunk(c01), _build_reg_chunk(c01), _build_tim_chunk(c01)


# ---------------------------------------------------------------------------
# Post-extraction sync helpers
# ---------------------------------------------------------------------------

def _prime_hdma_init_event(cpu_chunk: bytes, f01: bytes | None) -> bytes:
    """Schedule line-0 HDMA init before the first rendered frame.

    Our safe CPU defaults start at HC_RENDER_EVENT. At V_Counter=0 that
    skips snes9x's one allowed S9xStartHDMA() call for the upcoming visible
    frame, so color-math HDMA effects only appear on frame 2. If HDMA is
    enabled in FillRAM, schedule HC_HDMA_INIT_EVENT at Timings.HDMAInit
    instead.
    """
    if f01 is None or len(f01) < HDMAEN + 1 or f01[HDMAEN] == 0:
        return cpu_chunk
    out = bytearray(cpu_chunk)
    if len(out) != SNES_CPU_SIZE:
        return cpu_chunk
    v_counter = int.from_bytes(out[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4], "big")
    if v_counter != 0:
        return cpu_chunk
    out[CPU_OFF_WHICH_EVENT] = HC_HDMA_INIT_EVENT
    out[CPU_OFF_NEXT_EVENT:CPU_OFF_NEXT_EVENT + 4] = (20).to_bytes(4, "big")  # HDMAInit
    return bytes(out)


VBLANK_ENTRY_V_COUNTER = 225
VBLANK_NMI_TRIGGER_POS = 12
VBLANK_NEXT_EVENT_RENDER = 512
VBLANK_NEXT_EVENT_HDMA_INIT = 20


def _apply_vblank_entry_state(cpu_chunk: bytes, tim_chunk: bytes,
                              *,
                              cycles: int | None,
                              wram_refresh: int | None,
                              which_event: int | None,
                              next_event: int | None,
                              nmi_pending: int | None,
                              nmi_trigger_pos: int | None,
                              set_interlace: bool = True
                              ) -> tuple[bytes, bytes]:
    """Migrate (cpu, tim) to the post-vblank-entry shape native snes9x produces.

    Each parameter that is None is left untouched, so the legacy three-branch
    behavior is preserved exactly: the WAI HDMA branch (which only updates
    V_COUNTER/NMIPending/NMI_POS/Interlace) keeps cycles/event/next_event
    from the original C01.
    """
    out_cpu = bytearray(cpu_chunk)
    out_tim = bytearray(tim_chunk)
    if cycles is not None:
        out_cpu[CPU_OFF_CYCLES:CPU_OFF_CYCLES + 4] = cycles.to_bytes(4, "big")
    out_cpu[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4] = (
        VBLANK_ENTRY_V_COUNTER.to_bytes(4, "big")
    )
    if which_event is not None:
        out_cpu[CPU_OFF_WHICH_EVENT] = which_event
    if next_event is not None:
        out_cpu[CPU_OFF_NEXT_EVENT:CPU_OFF_NEXT_EVENT + 4] = next_event.to_bytes(4, "big")
    if nmi_pending is not None:
        out_cpu[CPU_OFF_NMI_PENDING] = nmi_pending
    if wram_refresh is not None:
        out_tim[TIM_OFF_WRAM_REFRESH:TIM_OFF_WRAM_REFRESH + 4] = wram_refresh.to_bytes(4, "big")
    if nmi_trigger_pos is not None:
        out_tim[32:36] = nmi_trigger_pos.to_bytes(4, "big")
    if set_interlace:
        out_tim[TIM_OFF_INTERLACE] = 1
    return bytes(out_cpu), bytes(out_tim)


def _sync_frame_boundary_nmi_state(cpu_chunk: bytes, tim_chunk: bytes,
                                   f01: bytes | None) -> tuple[bytes, bytes]:
    """Normalize SR16's frame-boundary WAI state to snes9x's save phase.

    SR16 title-screen saves in the hello-world microscope serialize C01 at
    V=0/HDMA-init while the 65816 is already waiting for the vblank NMI. Native
    snes9x snapshots taken at the same visible point are consistently captured
    at the vblank entry line (V=225) with NMIPending set and NMITriggerPos=12.
    Apply that migration only to this narrow WAI+NMI boundary state; ordinary
    in-game line-0 snapshots keep the C01 timing as-is.

    Four boundary shapes are recognized, each with its own native snes9x
    "post-vblank-entry" snapshot template (see ``_apply_vblank_entry_state``):

    1. **Title WAI + H/V IRQ live** — h_beam=v_beam=0 with H+V IRQ enabled but
       the timer mirror is still zero. Render-event with NMIPending=0.
    2. **WAI HDMA** — WHICH_EVENT=HDMA_INIT, next_event=20, in WAI. NMIPending
       latches to 1; cycles/wram_refresh preserved from C01.
    3. **FFV non-WAI HDMA** — HDMAEN set, not in WAI. Migrate to render entry
       (cycles=82, next_event=512, wram_refresh=534).
    4. **Super Bomberman 5 line-0 DMA** — MDMAEN set, no H-IRQ enable.
       cycles=2, HDMA-init scheduled at next_event=20, wram_refresh=538.
    """
    if f01 is None or len(f01) <= NMITIMEN:
        return cpu_chunk, tim_chunk
    if len(cpu_chunk) != SNES_CPU_SIZE or len(tim_chunk) != SNES_TIM_SIZE:
        return cpu_chunk, tim_chunk
    nmi_enabled = bool(f01[NMITIMEN] & 0x80)
    v_counter = int.from_bytes(
        cpu_chunk[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4], "big"
    )
    next_event = int.from_bytes(
        cpu_chunk[CPU_OFF_NEXT_EVENT:CPU_OFF_NEXT_EVENT + 4], "big"
    )
    nmi_pos = int.from_bytes(tim_chunk[32:36], "big")
    if not (nmi_enabled and v_counter == 0 and nmi_pos == 0xFFFF):
        return cpu_chunk, tim_chunk

    h_enabled = bool(f01[NMITIMEN] & 0x10)
    v_enabled = bool(f01[NMITIMEN] & 0x20)
    h_beam = f01[HTIMEL] | ((f01[HTIMEH] & 1) << 8)
    v_beam = f01[VTIMEL] | ((f01[VTIMEH] & 1) << 8)

    # Case 1: Title WAI + H/V IRQ live with zero timer mirror.
    # Some SR16 saves serialize exactly at the frame boundary with H/V IRQ
    # live but the timer mirror still zeroed. If snes9x resumes that shape
    # at line 0, the first visible frame misses the game's IRQ-driven screen
    # setup. Resume from the same vblank/render phase native snes9x reaches
    # after the first post-load frame; _sync_irq_timer_state then schedules
    # the first real IRQ for the following frame from the zero timer pair.
    if h_enabled and v_enabled and h_beam == 0 and v_beam == 0:
        return _apply_vblank_entry_state(
            cpu_chunk, tim_chunk,
            cycles=82, wram_refresh=534,
            which_event=HC_RENDER_EVENT, next_event=VBLANK_NEXT_EVENT_RENDER,
            nmi_pending=0, nmi_trigger_pos=None,
        )

    # All remaining cases require the C01 to already be at WHICH_EVENT=HDMA_INIT
    # with next_event=20 (the canonical "armed for vblank NMI" shape).
    if not (cpu_chunk[CPU_OFF_WHICH_EVENT] == HC_HDMA_INIT_EVENT
            and next_event == 20):
        return cpu_chunk, tim_chunk

    # Case 2: WAI HDMA — only V_COUNTER/NMIPending/NMI_POS/Interlace change.
    if cpu_chunk[CPU_OFF_WAITING_FOR_INTERRUPT] != 0:
        return _apply_vblank_entry_state(
            cpu_chunk, tim_chunk,
            cycles=None, wram_refresh=None,
            which_event=None, next_event=None,
            nmi_pending=1, nmi_trigger_pos=VBLANK_NMI_TRIGGER_POS,
        )

    # Case 3: FFV's frame-perfect title saves show a second SR16 boundary shape:
    # HDMA is active, the CPU is not in WAI, and native snes9x snapshots at
    # the same visible frame serialize the post-NMI vblank/render phase.
    if len(f01) > HDMAEN and f01[HDMAEN]:
        return _apply_vblank_entry_state(
            cpu_chunk, tim_chunk,
            cycles=82, wram_refresh=534,
            which_event=HC_RENDER_EVENT, next_event=VBLANK_NEXT_EVENT_RENDER,
            nmi_pending=None, nmi_trigger_pos=None,
        )

    # Case 4: Super Bomberman 5 exposes a third boundary shape: SR16
    # serializes at line 0 with general DMA ($420B) still armed. The
    # DMA/PPU payload is already in memory, but snes9x needs to resume
    # from vblank entry so the game's NMI handler runs before the first
    # visible scanline. Note: set_interlace=False here mirrors the
    # original branch, which left interlace untouched.
    if len(f01) > MDMAEN and f01[MDMAEN] and not (f01[NMITIMEN] & 0x10):
        return _apply_vblank_entry_state(
            cpu_chunk, tim_chunk,
            cycles=2, wram_refresh=538,
            which_event=HC_HDMA_INIT_EVENT, next_event=VBLANK_NEXT_EVENT_HDMA_INIT,
            nmi_pending=1, nmi_trigger_pos=VBLANK_NMI_TRIGGER_POS,
            set_interlace=False,
        )

    return cpu_chunk, tim_chunk


def _cycles_until_next_irq(cpu_chunk: bytes, tim_chunk: bytes,
                           h_cycle: int, v_pos: int) -> int:
    """Mirror snes9x's CyclesUntilNext() for H/V IRQ timer restoration."""
    cpu_cycles = int.from_bytes(cpu_chunk[CPU_OFF_CYCLES:CPU_OFF_CYCLES + 4], "big")
    cpu_v = int.from_bytes(cpu_chunk[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4], "big")
    h_max_master = int.from_bytes(tim_chunk[TIM_OFF_H_MAX_MASTER:TIM_OFF_H_MAX_MASTER + 4], "big")
    v_max = int.from_bytes(tim_chunk[TIM_OFF_V_MAX:TIM_OFF_V_MAX + 4], "big")

    total = 0
    if v_pos - cpu_v > 0:
        total += (v_pos - cpu_v) * h_max_master
    else:
        if v_pos == cpu_v and h_cycle > cpu_cycles:
            return h_cycle
        total += (v_max - cpu_v) * h_max_master
        total += v_pos * h_max_master
    total += h_cycle
    return total


def _sync_irq_timer_state(cpu_chunk: bytes, tim_chunk: bytes,
                          ppu_chunk: bytes, f01: bytes | None
                          ) -> tuple[bytes, bytes, bytes]:
    """Restore snes9x's IRQ timer scheduler from hardware register mirrors.

    Snapshot v11+ stores Timings.NextIRQTimer directly. Because our standalone
    TIM chunk is synthesized, H/V IRQs can be enabled in FillRAM/PPU while the
    scheduler still says "no IRQ pending". Super Metroid uses that IRQ for its
    HUD/screen split, so leaving it disabled makes the first displayed frames
    settle only after the game rewrites $4200/$4207-$420A.
    """
    if f01 is None or len(f01) <= VTIMEH:
        return cpu_chunk, tim_chunk, ppu_chunk
    if (len(cpu_chunk) != SNES_CPU_SIZE
            or len(tim_chunk) != SNES_TIM_SIZE
            or len(ppu_chunk) < PPU_OFF_HTIMER_POS):
        return cpu_chunk, tim_chunk, ppu_chunk

    irq_enable = f01[NMITIMEN]
    h_enabled = bool(irq_enable & 0x10)
    v_enabled = bool(irq_enable & 0x20)

    out_ppu = bytearray(ppu_chunk)
    out_tim = bytearray(tim_chunk)

    irq_trigger = int.from_bytes(tim_chunk[TIM_OFF_IRQ_TRIGGER:TIM_OFF_IRQ_TRIGGER + 4], "big")
    h_beam = f01[HTIMEL] | ((f01[HTIMEH] & 1) << 8)
    v_beam = f01[VTIMEL] | ((f01[VTIMEH] & 1) << 8)
    h_pos = h_beam * 4 + irq_trigger
    if h_beam == 0:
        h_pos -= 4
    if h_beam > 322:
        h_pos += 2
    if h_beam > 326:
        h_pos += 2

    out_ppu[PPU_OFF_HTIMER_ENABLED] = 1 if h_enabled else 0
    out_ppu[PPU_OFF_VTIMER_ENABLED] = 1 if v_enabled else 0
    out_ppu[PPU_OFF_HTIMER_POS:PPU_OFF_HTIMER_POS + 2] = h_pos.to_bytes(2, "big", signed=True)
    out_ppu[PPU_OFF_VTIMER_POS:PPU_OFF_VTIMER_POS + 2] = v_beam.to_bytes(2, "big", signed=True)
    out_ppu[PPU_OFF_IRQ_H_BEAM:PPU_OFF_IRQ_H_BEAM + 2] = h_beam.to_bytes(2, "big")
    out_ppu[PPU_OFF_IRQ_V_BEAM:PPU_OFF_IRQ_V_BEAM + 2] = v_beam.to_bytes(2, "big")

    v_max = int.from_bytes(tim_chunk[TIM_OFF_V_MAX:TIM_OFF_V_MAX + 4], "big")
    if v_enabled and v_beam >= v_max:
        next_irq = NO_IRQ_PENDING
    elif not h_enabled and not v_enabled:
        next_irq = NO_IRQ_PENDING
    elif h_enabled and not v_enabled:
        cpu_cycles = int.from_bytes(cpu_chunk[CPU_OFF_CYCLES:CPU_OFF_CYCLES + 4], "big")
        next_irq = h_pos
        if cpu_cycles > next_irq - irq_trigger:
            next_irq += int.from_bytes(tim_chunk[TIM_OFF_H_MAX:TIM_OFF_H_MAX + 4], "big")
    elif not h_enabled and v_enabled:
        next_irq = _cycles_until_next_irq(cpu_chunk, tim_chunk, irq_trigger - 4, v_beam)
    else:
        next_irq = _cycles_until_next_irq(cpu_chunk, tim_chunk, h_pos, v_beam)

    out_tim[TIM_OFF_NEXT_IRQ:TIM_OFF_NEXT_IRQ + 4] = next_irq.to_bytes(4, "big")
    return cpu_chunk, bytes(out_tim), bytes(out_ppu)
