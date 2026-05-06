"""Tests for cpu_state per-chunk builders and IRQ sync helpers."""
from __future__ import annotations

from converter.sr16_to_snes9x.state.cpu import (
    _build_reg_chunk, _build_cpu_chunk, _build_tim_chunk,
    _extract_cpu, _prime_hdma_init_event, _sync_frame_boundary_nmi_state,
)
from converter.common.constants import (
    SNES_CPU_SIZE, SNES_REG_SIZE, SNES_TIM_SIZE, SR16_C01_SIZE,
    HDMAEN, MDMAEN, NMITIMEN, HC_HDMA_INIT_EVENT, HC_RENDER_EVENT,
    CPU_OFF_CYCLES, CPU_OFF_FAST_ROM_SPEED, CPU_OFF_V_COUNTER,
    CPU_OFF_WHICH_EVENT, CPU_OFF_NEXT_EVENT,
    CPU_OFF_WAITING_FOR_INTERRUPT, CPU_OFF_NMI_PENDING,
    NO_IRQ_PENDING_INIT, TIM_OFF_WRAM_REFRESH, TIM_OFF_INTERLACE, TIM_OFF_NEXT_IRQ,
    SR16_REG_OFF_DB, SR16_REG_OFF_PC_FULL,
    C01_OFF_CYCLES, C01_OFF_WAITING_FOR_INTERRUPT,
    C01_OFF_WHICH_EVENT, C01_OFF_NEXT_EVENT,
    C01_OFF_V_COUNTER, C01_OFF_FAST_ROM_SPEED,
    C01_OFF_TIMINGS_H_MAX, C01_OFF_TIMINGS_V_MAX_M,
    C01_OFF_TIMINGS_V_MAX, C01_OFF_INTERLACE,
)


def _make_c01() -> bytes:
    """Synthesize a C01 with distinct values in every field we read."""
    c01 = bytearray(SR16_C01_SIZE)
    # REG fields
    c01[SR16_REG_OFF_DB] = 0x42
    c01[0x01:0x05] = (0x000000A5).to_bytes(4, "big")  # P
    c01[0x05:0x09] = (0x00001234).to_bytes(4, "big")  # A
    c01[0x09:0x0D] = (0x00005678).to_bytes(4, "big")  # D
    c01[0x0D:0x11] = (0x00001FE6).to_bytes(4, "big")  # S
    c01[0x11:0x15] = (0x00002468).to_bytes(4, "big")  # X
    c01[0x15:0x19] = (0x000013AC).to_bytes(4, "big")  # Y
    c01[SR16_REG_OFF_PC_FULL:SR16_REG_OFF_PC_FULL + 4] = (0x82DEAD).to_bytes(4, "big")
    # CPU/TIM
    c01[C01_OFF_CYCLES:C01_OFF_CYCLES + 4] = (0x100).to_bytes(4, "big")
    c01[C01_OFF_WAITING_FOR_INTERRUPT] = 1
    c01[C01_OFF_WHICH_EVENT] = 7
    c01[C01_OFF_NEXT_EVENT:C01_OFF_NEXT_EVENT + 4] = (20).to_bytes(4, "big")
    c01[C01_OFF_V_COUNTER:C01_OFF_V_COUNTER + 4] = (200).to_bytes(4, "big")
    c01[C01_OFF_FAST_ROM_SPEED:C01_OFF_FAST_ROM_SPEED + 4] = (8).to_bytes(4, "big")
    c01[C01_OFF_TIMINGS_H_MAX:C01_OFF_TIMINGS_H_MAX + 4] = (1364).to_bytes(4, "big")
    c01[C01_OFF_TIMINGS_V_MAX_M:C01_OFF_TIMINGS_V_MAX_M + 4] = (262).to_bytes(4, "big")
    c01[C01_OFF_TIMINGS_V_MAX:C01_OFF_TIMINGS_V_MAX + 4] = (262).to_bytes(4, "big")
    c01[C01_OFF_INTERLACE] = 1
    return bytes(c01)


# ---------------------------------------------------------------------------
# REG chunk
# ---------------------------------------------------------------------------

def test_build_reg_chunk_size_and_layout():
    reg = _build_reg_chunk(_make_c01())
    assert len(reg) == SNES_REG_SIZE
    # PB is high byte of pc_full = 0x82
    assert reg[0] == 0x82
    # DB
    assert reg[1] == 0x42
    # P (BE)
    assert reg[2:4] == (0xA5).to_bytes(2, "big")
    # PC = low 16 bits of pc_full = 0xDEAD
    assert reg[14:16] == (0xDEAD).to_bytes(2, "big")
    # A, D, S, X, Y
    assert reg[4:6] == (0x1234).to_bytes(2, "big")
    assert reg[6:8] == (0x5678).to_bytes(2, "big")
    assert reg[8:10] == (0x1FE6).to_bytes(2, "big")
    assert reg[10:12] == (0x2468).to_bytes(2, "big")
    assert reg[12:14] == (0x13AC).to_bytes(2, "big")


# ---------------------------------------------------------------------------
# CPU chunk
# ---------------------------------------------------------------------------

def test_build_cpu_chunk_size_and_defaults():
    cpu = _build_cpu_chunk(_make_c01())
    assert len(cpu) == SNES_CPU_SIZE
    # Cycles = 0x100 (BE)
    assert int.from_bytes(cpu[0:4], "big") == 0x100
    # V_Counter = 200
    assert int.from_bytes(cpu[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4], "big") == 200
    # Old SR16/snes9x event 7 is migrated to current HC_HDMA_INIT_EVENT.
    assert cpu[CPU_OFF_WHICH_EVENT] == HC_HDMA_INIT_EVENT
    assert int.from_bytes(cpu[CPU_OFF_NEXT_EVENT:CPU_OFF_NEXT_EVENT + 4], "big") == 20
    assert cpu[CPU_OFF_WAITING_FOR_INTERRUPT] == 1
    assert int.from_bytes(
        cpu[CPU_OFF_FAST_ROM_SPEED:CPU_OFF_FAST_ROM_SPEED + 4], "big"
    ) == 8


# ---------------------------------------------------------------------------
# TIM chunk
# ---------------------------------------------------------------------------

def test_build_tim_chunk_size_and_terminator():
    tim = _build_tim_chunk(_make_c01())
    assert len(tim) == SNES_TIM_SIZE
    # NextIRQTimer (last 4 bytes) is the "no IRQ pending init" sentinel
    assert int.from_bytes(tim[TIM_OFF_NEXT_IRQ:TIM_OFF_NEXT_IRQ + 4], "big") == NO_IRQ_PENDING_INIT


# ---------------------------------------------------------------------------
# _extract_cpu orchestrator
# ---------------------------------------------------------------------------

def test_extract_cpu_returns_three_chunks_with_correct_sizes():
    cpu, reg, tim = _extract_cpu(_make_c01())
    assert (len(cpu), len(reg), len(tim)) == (SNES_CPU_SIZE, SNES_REG_SIZE, SNES_TIM_SIZE)


# ---------------------------------------------------------------------------
# _prime_hdma_init_event
# ---------------------------------------------------------------------------

def test_prime_hdma_init_noop_without_f01():
    cpu = _build_cpu_chunk(_make_c01())
    out = _prime_hdma_init_event(cpu, None)
    assert out == cpu


def test_prime_hdma_init_noop_when_hdma_disabled():
    cpu = _build_cpu_chunk(_make_c01())
    f01 = bytearray(0x8000)
    f01[HDMAEN] = 0
    assert _prime_hdma_init_event(cpu, bytes(f01)) == cpu


def test_prime_hdma_init_noop_when_v_counter_nonzero():
    """V_Counter != 0 means we're not at line 0 — leave alone."""
    cpu = _build_cpu_chunk(_make_c01())   # V_Counter=200
    f01 = bytearray(0x8000)
    f01[HDMAEN] = 0xFF
    assert _prime_hdma_init_event(cpu, bytes(f01)) == cpu


def test_prime_hdma_init_promotes_to_hdma_event_at_v0():
    cpu = bytearray(_build_cpu_chunk(_make_c01()))
    cpu[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4] = (0).to_bytes(4, "big")
    f01 = bytearray(0x8000)
    f01[HDMAEN] = 0xFF
    out = _prime_hdma_init_event(bytes(cpu), bytes(f01))
    assert out[CPU_OFF_WHICH_EVENT] == HC_HDMA_INIT_EVENT
    # NextEvent rewritten to Timings.HDMAInit (20 cycles after start of line)
    assert int.from_bytes(out[CPU_OFF_NEXT_EVENT:CPU_OFF_NEXT_EVENT + 4], "big") == 20


def test_sync_frame_boundary_nmi_promotes_waiting_line0_to_vblank_entry():
    cpu = bytearray(_build_cpu_chunk(_make_c01()))
    cpu[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4] = (0).to_bytes(4, "big")
    tim = bytearray(_build_tim_chunk(_make_c01()))
    tim[32:36] = (0xFFFF).to_bytes(4, "big")
    f01 = bytearray(0x8000)
    f01[NMITIMEN] = 0x80

    out_cpu, out_tim = _sync_frame_boundary_nmi_state(bytes(cpu), bytes(tim), bytes(f01))

    assert int.from_bytes(out_cpu[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4], "big") == 225
    assert out_cpu[CPU_OFF_NMI_PENDING] == 1
    assert int.from_bytes(out_tim[32:36], "big") == 12
    assert out_tim[TIM_OFF_INTERLACE] == 1


def test_sync_frame_boundary_nmi_noop_when_cpu_is_not_waiting():
    cpu = bytearray(_build_cpu_chunk(_make_c01()))
    cpu[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4] = (0).to_bytes(4, "big")
    cpu[CPU_OFF_WAITING_FOR_INTERRUPT] = 0
    tim = _build_tim_chunk(_make_c01())
    f01 = bytearray(0x8000)
    f01[NMITIMEN] = 0x80

    out_cpu, out_tim = _sync_frame_boundary_nmi_state(bytes(cpu), tim, bytes(f01))

    assert out_cpu == bytes(cpu)
    assert out_tim == tim


def test_sync_frame_boundary_nmi_moves_active_hdma_line0_to_vblank_render_phase():
    cpu = bytearray(_build_cpu_chunk(_make_c01()))
    cpu[CPU_OFF_CYCLES:CPU_OFF_CYCLES + 4] = (12).to_bytes(4, "big")
    cpu[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4] = (0).to_bytes(4, "big")
    cpu[CPU_OFF_WAITING_FOR_INTERRUPT] = 0
    tim = bytearray(_build_tim_chunk(_make_c01()))
    tim[32:36] = (0xFFFF).to_bytes(4, "big")
    f01 = bytearray(0x8000)
    f01[NMITIMEN] = 0x80
    f01[HDMAEN] = 0x7F

    out_cpu, out_tim = _sync_frame_boundary_nmi_state(bytes(cpu), bytes(tim), bytes(f01))

    assert int.from_bytes(out_cpu[CPU_OFF_CYCLES:CPU_OFF_CYCLES + 4], "big") == 82
    assert int.from_bytes(out_cpu[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4], "big") == 225
    assert out_cpu[CPU_OFF_WHICH_EVENT] == HC_RENDER_EVENT
    assert int.from_bytes(out_cpu[CPU_OFF_NEXT_EVENT:CPU_OFF_NEXT_EVENT + 4], "big") == 512
    assert out_cpu[CPU_OFF_NMI_PENDING] == 0
    assert int.from_bytes(out_tim[TIM_OFF_WRAM_REFRESH:TIM_OFF_WRAM_REFRESH + 4], "big") == 534


def test_sync_frame_boundary_nmi_moves_active_mdma_line0_to_vblank_entry():
    cpu = bytearray(_build_cpu_chunk(_make_c01()))
    cpu[CPU_OFF_CYCLES:CPU_OFF_CYCLES + 4] = (18).to_bytes(4, "big")
    cpu[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4] = (0).to_bytes(4, "big")
    cpu[CPU_OFF_WAITING_FOR_INTERRUPT] = 0
    tim = bytearray(_build_tim_chunk(_make_c01()))
    tim[32:36] = (0xFFFF).to_bytes(4, "big")
    f01 = bytearray(0x8000)
    f01[NMITIMEN] = 0x80
    f01[MDMAEN] = 0x01

    out_cpu, out_tim = _sync_frame_boundary_nmi_state(bytes(cpu), bytes(tim), bytes(f01))

    assert int.from_bytes(out_cpu[CPU_OFF_CYCLES:CPU_OFF_CYCLES + 4], "big") == 2
    assert int.from_bytes(out_cpu[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4], "big") == 225
    assert out_cpu[CPU_OFF_WHICH_EVENT] == HC_HDMA_INIT_EVENT
    assert int.from_bytes(out_cpu[CPU_OFF_NEXT_EVENT:CPU_OFF_NEXT_EVENT + 4], "big") == 20
    assert out_cpu[CPU_OFF_NMI_PENDING] == 1
    assert int.from_bytes(out_tim[32:36], "big") == 12
    assert int.from_bytes(out_tim[TIM_OFF_WRAM_REFRESH:TIM_OFF_WRAM_REFRESH + 4], "big") == 538


def test_sync_frame_boundary_nmi_keeps_mdma_line0_when_hirq_is_live():
    cpu = bytearray(_build_cpu_chunk(_make_c01()))
    cpu[CPU_OFF_CYCLES:CPU_OFF_CYCLES + 4] = (4).to_bytes(4, "big")
    cpu[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4] = (0).to_bytes(4, "big")
    cpu[CPU_OFF_WAITING_FOR_INTERRUPT] = 0
    tim = bytearray(_build_tim_chunk(_make_c01()))
    tim[32:36] = (0xFFFF).to_bytes(4, "big")
    f01 = bytearray(0x8000)
    f01[NMITIMEN] = 0x90  # NMI + H-IRQ, as in DKC's line-0 MDMA saves.
    f01[MDMAEN] = 0x01

    out_cpu, out_tim = _sync_frame_boundary_nmi_state(bytes(cpu), bytes(tim), bytes(f01))

    assert out_cpu == bytes(cpu)
    assert out_tim == bytes(tim)


def test_sync_frame_boundary_nmi_moves_zeroed_hv_irq_line0_to_vblank_render():
    cpu = bytearray(_build_cpu_chunk(_make_c01()))
    cpu[CPU_OFF_CYCLES:CPU_OFF_CYCLES + 4] = (96).to_bytes(4, "big")
    cpu[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4] = (0).to_bytes(4, "big")
    cpu[CPU_OFF_WHICH_EVENT] = HC_RENDER_EVENT
    cpu[CPU_OFF_NEXT_EVENT:CPU_OFF_NEXT_EVENT + 4] = (192).to_bytes(4, "big")
    cpu[CPU_OFF_WAITING_FOR_INTERRUPT] = 0
    tim = bytearray(_build_tim_chunk(_make_c01()))
    tim[32:36] = (0xFFFF).to_bytes(4, "big")
    f01 = bytearray(0x8000)
    f01[NMITIMEN] = 0xB0  # NMI + H/V IRQ, with $4207-$420A left at zero.
    f01[MDMAEN] = 0x01

    out_cpu, out_tim = _sync_frame_boundary_nmi_state(bytes(cpu), bytes(tim), bytes(f01))

    assert int.from_bytes(out_cpu[CPU_OFF_CYCLES:CPU_OFF_CYCLES + 4], "big") == 82
    assert int.from_bytes(out_cpu[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4], "big") == 225
    assert out_cpu[CPU_OFF_WHICH_EVENT] == HC_RENDER_EVENT
    assert int.from_bytes(out_cpu[CPU_OFF_NEXT_EVENT:CPU_OFF_NEXT_EVENT + 4], "big") == 512
    assert out_cpu[CPU_OFF_NMI_PENDING] == 0
    assert int.from_bytes(out_tim[TIM_OFF_WRAM_REFRESH:TIM_OFF_WRAM_REFRESH + 4], "big") == 534
    assert out_tim[TIM_OFF_INTERLACE] == 1
