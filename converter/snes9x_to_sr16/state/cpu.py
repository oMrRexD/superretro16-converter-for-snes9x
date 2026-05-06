"""snes9x CPU(48B) + REG(16B) + TIM(70B) → SR16 C01(161B).

Reverse of ``converter.sr16_to_snes9x.state.cpu._extract_cpu``.
"""
from __future__ import annotations

from converter.common.constants import (
    SR16_C01_SIZE,
    SNES_CPU_SIZE, SNES_REG_SIZE, SNES_TIM_SIZE,
    SR16_REG_OFF_DB, SR16_REG_OFF_P, SR16_REG_OFF_A, SR16_REG_OFF_D,
    SR16_REG_OFF_S, SR16_REG_OFF_X, SR16_REG_OFF_Y, SR16_REG_OFF_PC_FULL,
    C01_OFF_CYCLES, C01_OFF_WAITING_FOR_INTERRUPT,
    C01_OFF_WHICH_EVENT, C01_OFF_NEXT_EVENT,
    C01_OFF_V_COUNTER, C01_OFF_FAST_ROM_SPEED,
    C01_OFF_TIMINGS_H_MAX, C01_OFF_TIMINGS_V_MAX_M,
    C01_OFF_TIMINGS_V_MAX, C01_OFF_TIMINGS_NMI,
    C01_OFF_TIMINGS_WRAM_REF, C01_OFF_INTERLACE,
    CPU_OFF_CYCLES, CPU_OFF_V_COUNTER, CPU_OFF_FAST_ROM_SPEED,
    CPU_OFF_WHICH_EVENT, CPU_OFF_NEXT_EVENT,
    CPU_OFF_WAITING_FOR_INTERRUPT,
    TIM_OFF_H_MAX, TIM_OFF_V_MAX, TIM_OFF_WRAM_REFRESH, TIM_OFF_INTERLACE,
)

# Reverse of the old-event migration table in converter.sr16_to_snes9x.state.cpu.
# v12 event numbers → old SR16/snes9x numbering.  The forward converter maps
# several old values to the same v12 value, so the reverse picks the first
# (lower) old value for each v12 value.
_V12_EVENT_TO_OLD = {
    1: 1,
    2: 2,
    3: 4,
    4: 6,
    5: 8,
    6: 10,
}


def _sr16_opcode_table_selector(p: int) -> int:
    """Return SR16's serialized CPU opcode-table selector for Registers.P.

    SR16 is based on an older snes9x core that serializes which 65816 opcode
    dispatch table is active.  The table is derived from the emulation flag
    and the M/X width bits in P; leaving it at zero only works for M=1/X=1.
    """
    if p & 0x100:
        return 0x00000100  # S9xOpcodesE1
    mx = p & 0x30
    if mx == 0x30:
        return 0x00000000  # S9xOpcodesM1X1
    if mx == 0x20:
        return 0x00000200  # S9xOpcodesM1X0
    if mx == 0x00:
        return 0x00000300  # S9xOpcodesM0X0
    return 0x00000400      # S9xOpcodesM0X1


def _be_u(buf: bytes, off: int, size: int) -> int:
    return int.from_bytes(buf[off:off + size], "big")


def _put_be(out: bytearray, off: int, val: int, size: int) -> None:
    out[off:off + size] = val.to_bytes(size, "big")


def build_c01(cpu: bytes, reg: bytes, tim: bytes) -> bytes:
    """Build SR16 C01 section (161B) from snes9x CPU + REG + TIM chunks."""
    if len(cpu) != SNES_CPU_SIZE:
        raise ValueError(f"CPU chunk size {len(cpu)} != {SNES_CPU_SIZE}")
    if len(reg) != SNES_REG_SIZE:
        raise ValueError(f"REG chunk size {len(reg)} != {SNES_REG_SIZE}")
    if len(tim) != SNES_TIM_SIZE:
        raise ValueError(f"TIM chunk size {len(tim)} != {SNES_TIM_SIZE}")

    out = bytearray(SR16_C01_SIZE)

    # --- Registers from REG ---
    pb = reg[0]
    db = reg[1]
    p = int.from_bytes(reg[2:4], "big")
    a = int.from_bytes(reg[4:6], "big")
    d = int.from_bytes(reg[6:8], "big")
    s = int.from_bytes(reg[8:10], "big")
    x = int.from_bytes(reg[10:12], "big")
    y = int.from_bytes(reg[12:14], "big")
    pc = int.from_bytes(reg[14:16], "big")
    pc_full = (pb << 16) | pc

    out[SR16_REG_OFF_DB] = db
    _put_be(out, SR16_REG_OFF_P, p, 4)
    _put_be(out, SR16_REG_OFF_A, a, 4)
    _put_be(out, SR16_REG_OFF_D, d, 4)
    _put_be(out, SR16_REG_OFF_S, s, 4)
    _put_be(out, SR16_REG_OFF_X, x, 4)
    _put_be(out, SR16_REG_OFF_Y, y, 4)
    _put_be(out, SR16_REG_OFF_PC_FULL, pc_full, 4)

    # --- CPU scheduler fields ---
    cycles = _be_u(cpu, CPU_OFF_CYCLES, 4)
    v_counter = _be_u(cpu, CPU_OFF_V_COUNTER, 4)
    flags = _be_u(cpu, 12, 4)
    irq_pending = _be_u(cpu, 16, 4)
    mem_speed = _be_u(cpu, 20, 4)
    mem_speed_x2 = _be_u(cpu, 24, 4)
    fast_rom = _be_u(cpu, CPU_OFF_FAST_ROM_SPEED, 4)
    in_dma = cpu[32]
    in_hdma = cpu[33]
    in_dma_or_hdma = cpu[34]
    in_wram_dma_or_hdma = cpu[35]
    hdma_ran_in_dma = cpu[36]
    which_event_v12 = cpu[CPU_OFF_WHICH_EVENT]
    next_event = _be_u(cpu, CPU_OFF_NEXT_EVENT, 4)
    wai = cpu[CPU_OFF_WAITING_FOR_INTERRUPT]

    _put_be(out, C01_OFF_CYCLES, cycles, 4)
    _put_be(out, 0x2D, flags, 4)
    out[0x35] = in_dma_or_hdma
    out[0x36] = in_wram_dma_or_hdma
    _put_be(out, C01_OFF_V_COUNTER, v_counter, 4)
    _put_be(out, 0x4C, mem_speed, 4)
    _put_be(out, 0x50, mem_speed_x2, 4)
    _put_be(out, C01_OFF_FAST_ROM_SPEED, fast_rom, 4)
    _put_be(out, 0x5D, irq_pending, 4)
    out[0x61] = in_dma
    out[0x62] = in_hdma
    out[0x63] = hdma_ran_in_dma
    out[C01_OFF_WHICH_EVENT] = _V12_EVENT_TO_OLD.get(
        which_event_v12, which_event_v12
    )
    _put_be(out, C01_OFF_NEXT_EVENT, next_event, 4)
    out[C01_OFF_WAITING_FOR_INTERRUPT] = 1 if wai else 0

    # PrevCycles — SR16 uses 0xFFFFFFFF but that's dangerous for snes9x;
    # for reverse direction we write what SR16 normally has.
    _put_be(out, 0x64, 0xFFFFFFFF, 4)  # PrevCycles at C01 offset 0x64

    # The old SR16 core stores the arithmetic condition flags separately from
    # Registers.P.  Leaving these zeroed makes the first executed branch use a
    # different Z/N/C/V state even though P itself was restored correctly.
    out[0x6D] = p & 0x01                # _Carry
    out[0x6E] = 0 if (p & 0x02) else 1  # _Zero (0 means Z flag set)
    out[0x6F] = p & 0x80                # _Negative
    out[0x70] = 1 if (p & 0x40) else 0  # _Overflow

    _put_be(out, 0x69, _sr16_opcode_table_selector(p), 4)  # Opcodes

    # CPUExecuting
    out[0x71] = 1

    # --- Timing fields from TIM ---
    h_max = _be_u(tim, TIM_OFF_H_MAX, 4)
    v_max_m = _be_u(tim, 8, 4)   # V_Max_Master at TIM offset 8
    v_max = _be_u(tim, TIM_OFF_V_MAX, 4)
    nmi_pos = _be_u(tim, 32, 4)  # NMITriggerPos at TIM offset 32
    wram_ref = _be_u(tim, TIM_OFF_WRAM_REFRESH, 4)
    interlace = tim[TIM_OFF_INTERLACE]

    _put_be(out, C01_OFF_TIMINGS_H_MAX, h_max, 4)
    _put_be(out, C01_OFF_TIMINGS_V_MAX_M, v_max_m, 4)
    _put_be(out, C01_OFF_TIMINGS_V_MAX, v_max, 4)
    _put_be(out, C01_OFF_TIMINGS_NMI, nmi_pos, 4)
    _put_be(out, C01_OFF_TIMINGS_WRAM_REF, wram_ref, 4)
    out[C01_OFF_INTERLACE] = interlace

    return bytes(out)
