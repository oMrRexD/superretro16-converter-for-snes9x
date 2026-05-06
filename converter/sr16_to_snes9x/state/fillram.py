"""Build snes9x-compatible FillRAM from SR16's F01 hardware mirror."""
from __future__ import annotations

from converter.common.constants import (
    SR16_F01_SIZE,
    CPU_OFF_V_COUNTER, CPU_OFF_NMI_PENDING,
    TIM_OFF_IRQ_TRIGGER,
    SND_OFF_TAIL,
)


def _snes9x_reset_fillram() -> bytearray:
    """Return snes9x's reset/open-bus FillRAM pattern."""
    out = bytearray(SR16_F01_SIZE)
    for page in range(0x80):
        start = page << 8
        out[start:start + 0x100] = bytes([page]) * 0x100

    out[0x1000:0x2000] = b"\x00" * 0x1000
    out[0x2100:0x2200] = b"\x00" * 0x100
    out[0x4000:0x4100] = b"\x00" * 0x100
    out[0x4200:0x4300] = b"\x00" * 0x100
    out[0x4201] = 0xFF
    out[0x4213] = 0xFF
    out[0x2126] = 0x01
    out[0x2128] = 0x01
    return out


def _restore_vram_data_latches(out: bytearray, ppu_chunk: bytes | None,
                               vram: bytes | None) -> None:
    """Rebuild $2118/$2119 mirrors from the saved VMA pointer and VRAM.

    snes9x stores write-only PPU ports in FillRAM as the last byte written to
    each port. SR16's F01 can leave VMDATAL/VMDATAH zero, but the matching VRAM
    bytes are still present. When VMA.High is set, the PPU increments the VMA
    address after the high-byte write, so the last written word is one increment
    behind the saved address.
    """
    if ppu_chunk is None or vram is None or len(ppu_chunk) < 10 or len(vram) < 0x10000:
        return
    vma_high = ppu_chunk[0] != 0
    increment = ppu_chunk[1] or 1
    address = int.from_bytes(ppu_chunk[2:4], "big")
    last_word = (address - increment) & 0x7FFF if vma_high else address & 0x7FFF
    vram_off = (last_word * 2) & 0xFFFF
    out[0x2118] = vram[vram_off]
    out[0x2119] = vram[(vram_off + 1) & 0xFFFF]


def _restore_apu_cpu_ports(out: bytearray, snd_chunk: bytes | None) -> None:
    """Keep $2140-$2143 aligned with the CPU->SMP ports in SND.

    SR16's F01 mirror can leave the CPU-side APU I/O ports zero even though
    AR1/SND still contains the command bytes the 65816 most recently wrote.
    Native snes9x snapshots mirror those bytes in FillRAM too; missing them
    can confuse sound drivers that poll the mailbox immediately after load.
    """
    if snd_chunk is None or len(snd_chunk) < SND_OFF_TAIL + 16:
        return
    out[0x2140:0x2144] = snd_chunk[SND_OFF_TAIL + 12:SND_OFF_TAIL + 16]


def _sync_nmi_status_latch(out: bytearray, cpu_chunk: bytes | None,
                           tim_chunk: bytes | None) -> None:
    """Keep $4210's NMI flag aligned with the migrated CPU/TIM NMI state."""
    if (
        cpu_chunk is None or tim_chunk is None
        or len(cpu_chunk) <= CPU_OFF_NMI_PENDING
        or len(tim_chunk) < TIM_OFF_IRQ_TRIGGER + 4
    ):
        return
    v_counter = int.from_bytes(
        cpu_chunk[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4], "big"
    )
    nmi_trigger = int.from_bytes(tim_chunk[32:36], "big")
    if v_counter >= 225 and (cpu_chunk[CPU_OFF_NMI_PENDING] or nmi_trigger == 0xFFFF):
        out[0x4210] |= 0x80
        out[0x213F] |= 0x80


def _build_fillram_chunk(
    f01: bytes,
    chip_names: set[str] | None = None,
    ppu_chunk: bytes | None = None,
    vram: bytes | None = None,
    cpu_chunk: bytes | None = None,
    tim_chunk: bytes | None = None,
    snd_chunk: bytes | None = None,
) -> bytes:
    """Translate SR16 F01 into the FIL chunk shape snes9x normally snapshots.

    SR16's F01 contains a broader hardware-register mirror. snes9x snapshots
    its ``Memory.FillRAM`` after reset/open-bus initialization, so untouched
    address pages contain their high-byte pattern (0x22 at $2200, 0x43 at
    $4300, etc.) rather than arbitrary mirror data. We preserve the live CPU,
    PPU and APU register windows that affect rendering/timing, and keep chip
    register RAM only when the corresponding chip chunk is present.
    """
    if len(f01) != SR16_F01_SIZE:
        return f01

    chip_names = chip_names or set()
    out = _snes9x_reset_fillram()

    # PPU registers + APU CPU I/O ports. Graphics and SPC mailbox state use
    # these mirrors immediately after snapshot load.
    out[0x2100:0x2200] = f01[0x2100:0x2200]

    # CPU control/status, timers, multiplier/divider and auto-joypad result.
    out[0x4200:0x4220] = f01[0x4200:0x4220]

    # Controller latch registers.
    out[0x4000:0x4018] = f01[0x4000:0x4018]

    if {"SA1", "SAR"} & chip_names:
        out[0x2200:0x2400] = f01[0x2200:0x2400]
    if "SFX" in chip_names:
        out[0x3000:0x4000] = f01[0x3000:0x4000]
    if "CX4" in chip_names:
        out[0x6000:0x8000] = f01[0x6000:0x8000]

    _restore_apu_cpu_ports(out, snd_chunk)
    _restore_vram_data_latches(out, ppu_chunk, vram)
    _sync_nmi_status_latch(out, cpu_chunk, tim_chunk)

    return bytes(out)
