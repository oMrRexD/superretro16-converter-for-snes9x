"""SMP/APU CPU state reconstruction for snes9x SND chunks."""
from __future__ import annotations

from converter.common.constants import (
    SND_SMP_BYTES, SR16_AR1_SIZE,
    A01_OFF_Y, A01_OFF_A, A01_OFF_X, A01_OFF_SP, A01_OFF_PSW, A01_OFF_PC,
    A01_OFF_IPL_ROM, A01_OFF_KEYED, A01_OFF_OUT_PORTS,
    A01_OFF_TIMER, A01_OFF_TIMER_TARGET, A01_OFF_TIMER_ENABLED,
    A01_OFF_DSP_REGS, A01_OFF_EXTRA_RAM,
    SPC_PORT_F4, SPC_DSPADDR, SPC_RAM_F8, SPC_RAM_F9,
    DSP_REG_FLG,
)
from .snd_binary import _be_u, _pack_le_i32

def _swap_mailbox_ports(ram: bytearray, a01: bytes) -> tuple[bytes, bytes]:
    """Place SMP->CPU ports into ram[$F4..$F7] and return both halves.

    The old SR16/Snes9x APU snapshot stores the two halves of the CPU/APU
    mailbox separately:
      - AR1[$F4-$F7] = CPU -> SMP ports (SMP reads them at $00F4..$00F7)
      - A01.OutPorts = SMP -> CPU ports (CPU reads them at $2140-$2143)

    Blargg's snes9x core serializes the first half at the SND tail as
    SNES::cpu.registers[4]; the second half lives in apuram[$F4-$F7].
    """
    cpu_to_smp = (
        bytes(ram[SPC_PORT_F4:SPC_PORT_F4 + 4])
        if len(ram) >= SPC_PORT_F4 + 4 else b"\x00" * 4
    )
    if len(a01) >= A01_OFF_OUT_PORTS + 4:
        smp_to_cpu = bytes(a01[A01_OFF_OUT_PORTS:A01_OFF_OUT_PORTS + 4])
    else:
        smp_to_cpu = cpu_to_smp
    if len(ram) >= SPC_PORT_F4 + 4:
        ram[SPC_PORT_F4:SPC_PORT_F4 + 4] = smp_to_cpu
    return cpu_to_smp, smp_to_cpu

def _smp_status_ram_byte(ram: bytearray, offset: int) -> int:
    """Return SMP $F8/$F9 status byte, ignoring SR16's stale $FF shadow."""
    if len(ram) <= offset:
        return 0
    return _smp_status_value(ram[offset])

def _smp_status_value(value: int) -> int:
    """Normalize an old-SR16 SMP status byte."""
    # $00F8/$00F9 are not regular RAM in Blargg's SMP core; they are serialized
    # as status.ram00f8/ram00f9. SR16's AR1 snapshots consistently leave the
    # raw bytes as 0xFF even when native snes9x saves report zero.
    return 0 if value == 0xFF else value

def _sync_apu_mmio_shadow(ram: bytearray, a01: bytes) -> None:
    """Normalize raw AR1 bytes for the SMP MMIO page ($F0-$FF)."""
    if len(ram) < 0x100:
        return
    dsp_regs = (
        a01[A01_OFF_DSP_REGS:A01_OFF_EXTRA_RAM]
        if len(a01) >= A01_OFF_EXTRA_RAM else b"\x00" * 128
    )
    ram[0xF0] = 0
    # $F1 is CONTROL. SR16's raw byte is reliable for timer/IPL flags.
    ram[0xF2] = ram[SPC_DSPADDR]
    ram[0xF3] = dsp_regs[ram[SPC_DSPADDR] & 0x7F] if dsp_regs else 0
    ram[SPC_RAM_F8] = _smp_status_ram_byte(ram, SPC_RAM_F8)
    ram[SPC_RAM_F9] = _smp_status_ram_byte(ram, SPC_RAM_F9)
    if len(a01) >= A01_OFF_TIMER_TARGET + 6:
        ram[0xFA] = _be_u(a01, A01_OFF_TIMER_TARGET, 2) & 0xFF
        ram[0xFB] = _be_u(a01, A01_OFF_TIMER_TARGET + 2, 2) & 0xFF
        ram[0xFC] = _be_u(a01, A01_OFF_TIMER_TARGET + 4, 2) & 0xFF
    ram[0xFD:0x100] = b"\x00\x00\x00"


# ---------------------------------------------------------------------------
# SMP block (164 B, 41 LE int32 fields)
# ---------------------------------------------------------------------------

def _looks_like_ipl_boot_snd(a01: bytes, ram: bytes) -> bool:
    """Detect an APU snapshot taken before the game sound driver starts.

    SR16 can serialize the SPC RAM at this point as a mostly-0xFF bootstrap
    pattern, while snes9x's own fresh snapshots keep the IPL-visible RAM clean
    apart from the boot mailbox. Treat only this very narrow state as reset-like
    so real music saves keep their AR1/SSZ data untouched.
    """
    if len(a01) < A01_OFF_EXTRA_RAM or len(ram) < SR16_AR1_SIZE:
        return False
    pc = _be_u(a01, A01_OFF_PC, 2)
    dsp_regs = a01[A01_OFF_DSP_REGS:A01_OFF_EXTRA_RAM]
    return (
        a01[A01_OFF_IPL_ROM] != 0
        and pc >= 0xFFC0
        and a01[A01_OFF_KEYED] == 0
        and all(
            value == 0 or (index == DSP_REG_FLG and value in (0x60, 0xE0))
            for index, value in enumerate(dsp_regs)
        )
        and ram.count(0xFF) >= 0x4000
    )

def _build_smp_state(a01: bytes, ram: bytearray, *,
                     timer_read_counters: bytes | None = None,
                     ipl_boot: bool = False) -> bytes:
    """Build the 164B SMP block from SR16 A01 + AR1 zero-page.

    Field index -> snes9x SMP::save_state name:
      0=clock 1=opcode_number 2=opcode_cycle
      3=pc 4=sp 5=a 6=x 7=y
      8..15 = p.n p.v p.p p.b p.h p.i p.z p.c
      16=iplrom_enable 17=dsp_addr 18=ram00f8 19=ram00f9
      20..24 = timer0.{enable,target,stage1,stage2,stage3}
      25..29 = timer1, 30..34 = timer2
      35=rd 36=wr 37=dp 38=sp 39=ya 40=bit
    """
    smp = bytearray(SND_SMP_BYTES)

    pc = 0
    if len(a01) >= A01_OFF_PC + 2:
        spc_y = a01[A01_OFF_Y]
        spc_a = a01[A01_OFF_A]
        spc_x = a01[A01_OFF_X]
        sp    = a01[A01_OFF_SP]
        psw   = a01[A01_OFF_PSW]
        pc    = _be_u(a01, A01_OFF_PC, 2)
        ya    = (spc_y << 8) | spc_a   # YA = Y high, A low (host LE union)
        _pack_le_i32(smp, 3 * 4, pc)
        _pack_le_i32(smp, 4 * 4, sp)
        _pack_le_i32(smp, 5 * 4, spc_a)
        _pack_le_i32(smp, 6 * 4, spc_x)
        _pack_le_i32(smp, 7 * 4, spc_y)
        _pack_le_i32(smp, 8 * 4,  1 if psw & 0x80 else 0)
        _pack_le_i32(smp, 9 * 4,  1 if psw & 0x40 else 0)
        _pack_le_i32(smp, 10 * 4, 1 if psw & 0x20 else 0)
        _pack_le_i32(smp, 11 * 4, 1 if psw & 0x10 else 0)
        _pack_le_i32(smp, 12 * 4, 1 if psw & 0x08 else 0)
        _pack_le_i32(smp, 13 * 4, 1 if psw & 0x04 else 0)
        _pack_le_i32(smp, 14 * 4, 1 if psw & 0x02 else 0)
        _pack_le_i32(smp, 15 * 4, 1 if psw & 0x01 else 0)
        _pack_le_i32(smp, 38 * 4, sp)        # sp scratch
        _pack_le_i32(smp, 39 * 4, ya)        # ya scratch
    else:
        _pack_le_i32(smp, 4 * 4, 0xEF)       # fallback SP
        _pack_le_i32(smp, 38 * 4, 0xEF)

    # clock=0: snes9x's smp.clock is relative to current scheduler position.
    # Any large value would make the scheduler skip SMP execution (the bug
    # that left SPC700 idle for the first ~10 frames in v5).
    _pack_le_i32(smp, 0, 0)
    if ipl_boot:
        # Native snes9x snapshots captured in the IPL ROM have a deterministic
        # opcode number for the two boot PCs observed while the hello-world test
        # ROM waits for SPC startup.
        _pack_le_i32(smp, 1 * 4, 208 if pc == 0xFFCF else 120)

    _pack_le_i32(smp, 16 * 4, a01[A01_OFF_IPL_ROM] if len(a01) > A01_OFF_IPL_ROM else 0)
    if len(ram) >= 0x100:
        _pack_le_i32(smp, 17 * 4, ram[SPC_DSPADDR])
        _pack_le_i32(smp, 18 * 4, _smp_status_ram_byte(ram, SPC_RAM_F8))
        _pack_le_i32(smp, 19 * 4, _smp_status_ram_byte(ram, SPC_RAM_F9))

    if len(a01) >= A01_OFF_DSP_REGS:
        timers = [
            _be_u(a01, A01_OFF_TIMER + i * 2, 2) for i in range(3)
        ]
        targets = [
            _be_u(a01, A01_OFF_TIMER_TARGET + i * 2, 2) for i in range(3)
        ]
        enabled = a01[A01_OFF_TIMER_ENABLED:A01_OFF_TIMER_ENABLED + 3]
        for i in range(3):
            base = (20 + i * 5) * 4
            _pack_le_i32(smp, base,     1 if enabled[i] else 0)         # enable
            target = targets[i] & 0xFF
            _pack_le_i32(smp, base + 4, target)                         # target
            # A01.Timer[] is the old divider progress. The readable $FD-$FF
            # counters live in AR1's MMIO page; preserve them separately so
            # engines that poll timer ticks immediately after load (FFV battle
            # SFX) do not see a fabricated zero.
            _pack_le_i32(smp, base + 8, 0)                               # stage1
            _pack_le_i32(smp, base + 12, timers[i] % (target or 256))     # stage2
            stage3 = 0
            if timer_read_counters and i < len(timer_read_counters):
                stage3 = _smp_status_value(timer_read_counters[i]) & 0x0F
            _pack_le_i32(smp, base + 16, stage3)                         # stage3

    return bytes(smp)


# ---------------------------------------------------------------------------
# DSP state (642 B)
# ---------------------------------------------------------------------------
