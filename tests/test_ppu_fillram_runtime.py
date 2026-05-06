"""Tests for runtime PPU/FIL latch reconstruction."""
from __future__ import annotations

from converter.sr16_to_snes9x.state.fillram import _build_fillram_chunk
from converter.sr16_to_snes9x.state.ppu import _sync_ppu_postload_runtime
from converter.common.constants import (
    SR16_F01_SIZE, SNES_CPU_SIZE, SNES_PPU_SIZE, SNES_TIM_SIZE,
    SNES_SND_SIZE, SND_OFF_TAIL,
    CPU_OFF_V_COUNTER, CPU_OFF_NMI_PENDING,
    PPU_OFF_CGADD, PPU_OFF_CGDATA, PPU_OFF_CG_SAVED_BYTE,
    PPU_OFF_HBEAM_LATCH, PPU_OFF_GUN_V_LATCH,
    PPU_OFF_WIN1_LEFT, PPU_OFF_WIN2_LEFT, PPU_OFF_RECOMPUTE_CLIP,
    PPU_OFF_HDMA_BYTE, HDMAEN,
)


def test_ppu_runtime_rebuilds_palette_and_latch_defaults():
    ppu = bytearray(SNES_PPU_SIZE)
    f01 = bytearray(SR16_F01_SIZE)
    ppu[PPU_OFF_CGADD] = 4
    ppu[PPU_OFF_CGDATA + 3 * 2:PPU_OFF_CGDATA + 3 * 2 + 2] = b"\x42\x1f"
    ppu[PPU_OFF_HBEAM_LATCH:PPU_OFF_HBEAM_LATCH + 2] = (302).to_bytes(2, "big")
    ppu[PPU_OFF_WIN1_LEFT] = 1
    ppu[PPU_OFF_WIN2_LEFT] = 1
    ppu[PPU_OFF_RECOMPUTE_CLIP] = 1

    out = _sync_ppu_postload_runtime(bytes(ppu), bytes(f01))

    assert out[PPU_OFF_CG_SAVED_BYTE] == 0x1F
    assert int.from_bytes(out[PPU_OFF_HBEAM_LATCH:PPU_OFF_HBEAM_LATCH + 2], "big") == 305
    assert int.from_bytes(out[PPU_OFF_GUN_V_LATCH:PPU_OFF_GUN_V_LATCH + 2], "big") == 1000
    assert out[PPU_OFF_WIN1_LEFT] == 0
    assert out[PPU_OFF_WIN2_LEFT] == 0
    assert out[PPU_OFF_RECOMPUTE_CLIP] == 0


def test_fillram_rebuilds_vram_ports_and_nmi_status():
    f01 = bytearray(SR16_F01_SIZE)
    f01[0x4210] = 0x02

    ppu = bytearray(SNES_PPU_SIZE)
    ppu[0] = 1       # VMA.High: increment after high byte
    ppu[1] = 1       # VMA.Increment
    ppu[2:4] = (0x11D6).to_bytes(2, "big")

    vram = bytearray(0x10000)
    vram[((0x11D6 - 1) * 2) & 0xFFFF:(((0x11D6 - 1) * 2) & 0xFFFF) + 2] = b"\x21\x20"

    cpu = bytearray(SNES_CPU_SIZE)
    cpu[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4] = (225).to_bytes(4, "big")
    cpu[CPU_OFF_NMI_PENDING] = 1

    tim = bytearray(SNES_TIM_SIZE)
    tim[32:36] = (12).to_bytes(4, "big")

    out = _build_fillram_chunk(bytes(f01), set(), bytes(ppu), bytes(vram), bytes(cpu), bytes(tim))

    assert out[0x2118:0x211A] == b"\x21\x20"
    assert out[0x4210] == 0x82
    assert out[0x213F] == 0x80


def test_fillram_restores_apu_cpu_ports_from_snd_tail():
    f01 = bytearray(SR16_F01_SIZE)
    snd = bytearray(SNES_SND_SIZE)
    snd[SND_OFF_TAIL + 12:SND_OFF_TAIL + 16] = b"\x00\x00\x55\x55"

    out = _build_fillram_chunk(bytes(f01), snd_chunk=bytes(snd))

    assert out[0x2140:0x2144] == b"\x00\x00\x55\x55"


def test_ppu_hdma_runtime_only_restored_at_line0():
    ppu = bytearray(SNES_PPU_SIZE)
    f01 = bytearray(SR16_F01_SIZE)
    f01[HDMAEN] = 0x7F

    line0_cpu = bytearray(SNES_CPU_SIZE)
    vblank_cpu = bytearray(SNES_CPU_SIZE)
    vblank_cpu[CPU_OFF_V_COUNTER:CPU_OFF_V_COUNTER + 4] = (225).to_bytes(4, "big")

    line0 = _sync_ppu_postload_runtime(bytes(ppu), bytes(f01), bytes(line0_cpu))
    vblank = _sync_ppu_postload_runtime(bytes(ppu), bytes(f01), bytes(vblank_cpu))

    assert line0[PPU_OFF_HDMA_BYTE] == 0x7F
    assert vblank[PPU_OFF_HDMA_BYTE] == 0
