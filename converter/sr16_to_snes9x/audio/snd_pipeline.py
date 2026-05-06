"""Top-level SR16 APU sections to snes9x SND orchestration."""
from __future__ import annotations

from converter.common.constants import SR16_AR1_SIZE
from converter.common.format.sr16 import SR16Save
from .snd_assembly import _assemble_snd
from .snd_dsp import _build_dsp_state
from .snd_old_spc import _build_old_spc_safe_snd, _convert_old_spc_to_snd
from .snd_smp import (
    _build_smp_state,
    _looks_like_ipl_boot_snd,
    _swap_mailbox_ports,
    _sync_apu_mmio_shadow,
)

def _extract_snd(sr16: SR16Save) -> bytes:
    """Build snes9x SND chunk (66560B) from SR16 AR1 (SPC RAM) + A01 (+ SSZ).

    snes9x SND layout (from snes9x/apu/apu.cpp S9xAPUSaveState):
      [0..65535]     SPC RAM (64 KB)            -- from SR16 AR1
      [65536..65699] SMP::save_state            -- 41 LE int32 = 164 B
      [65700..66341] DSP::save_state            -- 642 B
      [66342..66345] reference_time (LE int32)
      [66346..66349] remainder       (LE int32)
      [66350..66353] dsp.clock       (LE int32)
      [66354..66357] CPU.registers[4]
      [66358..66559] zero padding

    SR16 A01 (248B) field map used by this converter:
      [0x04..0x06] Register_YA.W (BE: byte0=Y, byte1=A)
      [0x06]       X    [0x07] SP    [0x08] PSW
      [0x0D..0x0F] PC (BE)
      [0x1F]       ShowROM
      [0x24]       KeyedChannels
      [0x29..0x2F] Timer[3]      (BE uint16)
      [0x2F..0x35] TimerTarget[3] (BE uint16)
      [0x35..0x38] TimerEnabled[3]
      [0x38..0xB8] DSP[128]
      [0xB8..0xF8] ExtraRAM[64]
    """
    apu_ram = sr16.by_code("AR1")
    a01_section = sr16.by_code("A01")
    spc_section = sr16.by_code("SPC")
    if (apu_ram is None or a01_section is None) and spc_section is not None:
        # Top Gear 3000/DSP-4 samples use SR16's older combined SPC snapshot
        # instead of A01 + AR1 + SSZ. Convert the old Blargg APU state to the
        # current snes9x SND layout; raw truncation leaves SMP/DSP fields shifted
        # and can make snes9x hang for several seconds on load.
        converted = _convert_old_spc_to_snd(spc_section.data)
        if converted is not None:
            return converted
        return _build_old_spc_safe_snd(spc_section.data)

    ram = bytearray(apu_ram.data if apu_ram else b"\x00" * SR16_AR1_SIZE)
    a01 = a01_section.data if a01_section else b""
    ssz_section = sr16.by_code("SSZ")
    ssz = ssz_section.data if ssz_section else b""

    ipl_boot = _looks_like_ipl_boot_snd(a01, ram)
    if ipl_boot:
        ram = bytearray(SR16_AR1_SIZE)

    timer_read_counters = bytes(ram[0xFD:0x100]) if len(ram) >= 0x100 else b"\x00" * 3
    cpu_to_smp_ports, _smp_to_cpu = _swap_mailbox_ports(ram, a01)
    _sync_apu_mmio_shadow(ram, a01)
    smp = _build_smp_state(
        a01, ram, timer_read_counters=timer_read_counters, ipl_boot=ipl_boot
    )
    dsp = _build_dsp_state(a01, ram, ssz, ipl_boot=ipl_boot)
    return _assemble_snd(ram, smp, dsp, cpu_to_smp_ports)


# ---------------------------------------------------------------------------
# Legacy SR16 SPC chunk path (Top Gear 3000)
# ---------------------------------------------------------------------------
