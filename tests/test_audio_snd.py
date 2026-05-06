"""Tests for audio_snd helper functions (post-decomposition)."""
from __future__ import annotations
import struct

from converter.sr16_to_snes9x.audio.snd import (
    _default_ctl,
    _be_u, _be_s16,
    _pack_le_i32, _pack_le_u16, _pack_le_i16,
    _swap_mailbox_ports,
    _sync_apu_mmio_shadow,
    _build_smp_state,
    _build_dsp_state,
    _looks_like_ipl_boot_snd,
    _assemble_snd,
    _build_old_spc_safe_snd,
    _old_spc_dsp_state_plausible,
)
from converter.common.constants import (
    SR16_AR1_SIZE, SND_SMP_BYTES, SND_DSP_BYTES, SND_TAIL_BYTES,
    SNES_SND_SIZE, SPC_PORT_F4, A01_OFF_OUT_PORTS,
    A01_OFF_PC, A01_OFF_Y, A01_OFF_A, A01_OFF_X, A01_OFF_SP, A01_OFF_PSW,
    A01_OFF_IPL_ROM, A01_OFF_KEYED, A01_OFF_DSP_REGS,
    A01_OFF_TIMER, A01_OFF_TIMER_TARGET, A01_OFF_TIMER_ENABLED,
    SPC_RAM_F8, SPC_RAM_F9,
    DSP_OFF_EXTERNAL_REGS, DSP_OFF_MISC,
    DSP_REG_FLG, DSP_REG_NON, DSP_REG_DIR,
    DSP_MISC_T_ECHO_EN, DSP_MISC_ENVX_BUF, DSP_MISC_OUTX_BUF,
    DSP_OFF_VOICES, DSP_VOICE_STRIDE, VOICE_OFF_ENV, VOICE_OFF_BRR_ADDR,
    VOICE_OFF_BRR_OFFSET,
    VOICE_OFF_T_ENVX_OUT,
    SSZ_VOICE_BASE, SSZ_VOICE_STRIDE, SSZ_EXT_BASE, SSZ_EXT_STRIDE,
    SSZ_EXT_OUT_SAMPLE, SSZ_EXT_ENV,
)


# ---------------------------------------------------------------------------
# Endian helpers
# ---------------------------------------------------------------------------

def test_be_u_basic():
    assert _be_u(b"\x12\x34", 0, 2) == 0x1234
    assert _be_u(b"\x00\xff\xab", 1, 2) == 0xFFAB


def test_be_s16_signed():
    assert _be_s16(b"\x80\x00", 0) == -32768
    assert _be_s16(b"\x7f\xff", 0) == 32767
    assert _be_s16(b"\xff\xff", 0) == -1


def test_pack_le_helpers():
    buf = bytearray(8)
    _pack_le_i32(buf, 0, 0x12345678)
    assert buf[0:4] == b"\x78\x56\x34\x12"

    _pack_le_u16(buf, 4, 0xBEEF)
    assert buf[4:6] == b"\xef\xbe"

    _pack_le_i16(buf, 6, -1)
    assert buf[6:8] == b"\xff\xff"


def test_pack_le_i16_clamps():
    buf = bytearray(2)
    _pack_le_i16(buf, 0, 99999)
    val, = struct.unpack("<h", buf)
    assert val == 32767
    _pack_le_i16(buf, 0, -99999)
    val, = struct.unpack("<h", buf)
    assert val == -32768


# ---------------------------------------------------------------------------
# Mailbox swap
# ---------------------------------------------------------------------------

def test_swap_mailbox_ports_writes_smp_to_cpu_into_ram():
    ram = bytearray(SR16_AR1_SIZE)
    ram[SPC_PORT_F4:SPC_PORT_F4 + 4] = b"\xaa\xbb\xcc\xdd"   # CPU->SMP

    a01 = bytearray(0xF8)
    a01[A01_OFF_OUT_PORTS:A01_OFF_OUT_PORTS + 4] = b"\x11\x22\x33\x44"  # SMP->CPU

    cpu_to_smp, smp_to_cpu = _swap_mailbox_ports(ram, bytes(a01))
    assert cpu_to_smp == b"\xaa\xbb\xcc\xdd"
    assert smp_to_cpu == b"\x11\x22\x33\x44"
    # ram now holds SMP->CPU at $F4 (visible to SPC code on resume)
    assert ram[SPC_PORT_F4:SPC_PORT_F4 + 4] == b"\x11\x22\x33\x44"


def test_swap_mailbox_ports_short_a01_falls_back():
    ram = bytearray(SR16_AR1_SIZE)
    ram[SPC_PORT_F4:SPC_PORT_F4 + 4] = b"\x01\x02\x03\x04"
    cpu_to_smp, smp_to_cpu = _swap_mailbox_ports(ram, b"")
    assert cpu_to_smp == b"\x01\x02\x03\x04"
    assert smp_to_cpu == cpu_to_smp


def test_sync_apu_mmio_shadow_normalizes_non_ram_registers():
    ram = bytearray([0xFF]) * SR16_AR1_SIZE
    ram[0xF1] = 0x01
    ram[0xF2] = DSP_REG_FLG
    a01 = bytearray(0xF8)
    a01[A01_OFF_DSP_REGS + DSP_REG_FLG] = 0x60
    a01[A01_OFF_TIMER_TARGET:A01_OFF_TIMER_TARGET + 6] = (
        b"\x00\x24\x00\x80\x00\x00"
    )

    _sync_apu_mmio_shadow(ram, bytes(a01))

    assert ram[0xF0:0xF4] == bytes.fromhex("00016c60")
    assert ram[0xF8:0x100] == bytes.fromhex("0000248000000000")


# ---------------------------------------------------------------------------
# SMP state shape
# ---------------------------------------------------------------------------

def _make_a01_minimal() -> bytes:
    """Minimal A01 with non-zero CPU register state."""
    a01 = bytearray(0xF8)
    a01[A01_OFF_Y]   = 0x05
    a01[A01_OFF_A]   = 0x42
    a01[A01_OFF_X]   = 0x10
    a01[A01_OFF_SP]  = 0xEF
    a01[A01_OFF_PSW] = 0xA5  # bits 7,5,2,0 set
    a01[A01_OFF_PC:A01_OFF_PC + 2] = (0x1234).to_bytes(2, "big")
    return bytes(a01)


def test_build_smp_state_size_and_register_packing():
    a01 = _make_a01_minimal()
    ram = bytearray(SR16_AR1_SIZE)
    smp = _build_smp_state(a01, ram)
    assert len(smp) == SND_SMP_BYTES
    # field 3 = pc, field 4 = sp, field 5 = a, field 6 = x, field 7 = y
    assert struct.unpack_from("<i", smp, 3 * 4)[0] == 0x1234
    assert struct.unpack_from("<i", smp, 4 * 4)[0] == 0xEF
    assert struct.unpack_from("<i", smp, 5 * 4)[0] == 0x42
    assert struct.unpack_from("<i", smp, 6 * 4)[0] == 0x10
    assert struct.unpack_from("<i", smp, 7 * 4)[0] == 0x05
    # PSW bit unpacking: 0xA5 = 10100101
    assert struct.unpack_from("<i", smp, 8 * 4)[0] == 1   # n
    assert struct.unpack_from("<i", smp, 9 * 4)[0] == 0   # v
    assert struct.unpack_from("<i", smp, 10 * 4)[0] == 1  # p
    assert struct.unpack_from("<i", smp, 11 * 4)[0] == 0  # b
    assert struct.unpack_from("<i", smp, 12 * 4)[0] == 0  # h
    assert struct.unpack_from("<i", smp, 13 * 4)[0] == 1  # i
    assert struct.unpack_from("<i", smp, 14 * 4)[0] == 0  # z
    assert struct.unpack_from("<i", smp, 15 * 4)[0] == 1  # c
    # ya = (Y << 8) | A = 0x0542 in field 39
    assert struct.unpack_from("<i", smp, 39 * 4)[0] == 0x0542


def test_build_smp_state_short_a01_uses_fallback_sp():
    smp = _build_smp_state(b"", bytearray(SR16_AR1_SIZE))
    assert len(smp) == SND_SMP_BYTES
    # Fallback writes SP=0xEF in fields 4 and 38, others zero
    assert struct.unpack_from("<i", smp, 4 * 4)[0] == 0xEF
    assert struct.unpack_from("<i", smp, 38 * 4)[0] == 0xEF
    # clock (field 0) is 0
    assert struct.unpack_from("<i", smp, 0)[0] == 0


def test_build_smp_state_sanitizes_stale_f8_f9_shadow():
    a01 = _make_a01_minimal()
    ram = bytearray(SR16_AR1_SIZE)
    ram[SPC_RAM_F8] = 0xFF
    ram[SPC_RAM_F9] = 0xFF

    smp = _build_smp_state(a01, ram)

    assert struct.unpack_from("<i", smp, 18 * 4)[0] == 0
    assert struct.unpack_from("<i", smp, 19 * 4)[0] == 0


def test_build_smp_state_timer_divider_does_not_create_pending_tick():
    a01 = bytearray(_make_a01_minimal())
    a01[A01_OFF_TIMER:A01_OFF_TIMER + 2] = (0x001C).to_bytes(2, "big")
    a01[A01_OFF_TIMER_TARGET:A01_OFF_TIMER_TARGET + 2] = (0x0024).to_bytes(2, "big")
    a01[A01_OFF_TIMER_ENABLED] = 1

    smp = _build_smp_state(bytes(a01), bytearray(SR16_AR1_SIZE))

    timer0 = [struct.unpack_from("<i", smp, (20 + i) * 4)[0] for i in range(5)]
    assert timer0 == [1, 0x24, 0, 0x1C, 0]


def test_build_smp_state_preserves_timer_read_counters_from_ar1():
    a01 = bytearray(_make_a01_minimal())
    a01[A01_OFF_TIMER_TARGET:A01_OFF_TIMER_TARGET + 6] = (
        b"\x00\x24\x00\x80\x00\x00"
    )
    a01[A01_OFF_TIMER_ENABLED] = 1

    smp = _build_smp_state(
        bytes(a01),
        bytearray(SR16_AR1_SIZE),
        timer_read_counters=b"\x00\x09\xff",
    )

    timer0 = [struct.unpack_from("<i", smp, (20 + i) * 4)[0] for i in range(5)]
    timer1 = [struct.unpack_from("<i", smp, (25 + i) * 4)[0] for i in range(5)]
    timer2 = [struct.unpack_from("<i", smp, (30 + i) * 4)[0] for i in range(5)]
    assert timer0[-1] == 0
    assert timer1[-1] == 9
    assert timer2[-1] == 0


def test_ipl_boot_detection_accepts_sr16_reset_apu_pattern():
    a01 = bytearray(0xF8)
    a01[A01_OFF_PC:A01_OFF_PC + 2] = (0xFFD2).to_bytes(2, "big")
    a01[A01_OFF_IPL_ROM] = 1
    a01[A01_OFF_KEYED] = 0
    a01[A01_OFF_DSP_REGS + DSP_REG_FLG] = 0x60
    ram = bytearray([0xFF]) * SR16_AR1_SIZE

    assert _looks_like_ipl_boot_snd(bytes(a01), bytes(ram))


def test_ipl_boot_dsp_state_matches_snes9x_power_on_shape():
    dsp = _build_dsp_state(bytes(0xF8), bytearray(SR16_AR1_SIZE), b"", ipl_boot=True)

    assert len(dsp) == SND_DSP_BYTES
    assert dsp[66] == 1
    assert dsp[82] == 1
    assert dsp[DSP_REG_FLG] == 0xE0
    assert dsp[DSP_OFF_MISC] == 1
    assert dsp[DSP_MISC_T_ECHO_EN] == 0xE0
    assert dsp[DSP_OFF_EXTERNAL_REGS:DSP_OFF_EXTERNAL_REGS + 4] == b"\x45\x8b\x5a\x9a"


def test_build_dsp_state_seeds_ssz_envx_outx_and_noise_voice():
    a01 = bytearray(0xF8)
    a01[A01_OFF_KEYED] = 0x01
    a01[A01_OFF_DSP_REGS + DSP_REG_NON] = 0x01
    a01[A01_OFF_DSP_REGS + DSP_REG_DIR] = 0x00
    ssz = bytearray(1281)
    base = SSZ_VOICE_BASE
    ext = SSZ_EXT_BASE
    ssz[base:base + 4] = (3).to_bytes(4, "big")
    ssz[ext + SSZ_EXT_ENV:ext + SSZ_EXT_ENV + 4] = (0x700).to_bytes(4, "big")
    ssz[ext + SSZ_EXT_OUT_SAMPLE:ext + SSZ_EXT_OUT_SAMPLE + 2] = (
        (-0x1200).to_bytes(2, "big", signed=True)
    )

    dsp = _build_dsp_state(bytes(a01), bytearray(SR16_AR1_SIZE), bytes(ssz))

    voice = DSP_OFF_VOICES
    assert dsp[VOICE_OFF_ENV + voice:VOICE_OFF_ENV + voice + 2] == b"\x00\x07"
    assert dsp[voice + VOICE_OFF_T_ENVX_OUT] == 0x70
    assert dsp[0x08] == 0x70
    assert dsp[0x09] == 0xEE
    assert dsp[DSP_MISC_ENVX_BUF] == 0x70
    assert dsp[DSP_MISC_OUTX_BUF] == 0xEE
    assert struct.unpack_from("<H", dsp, DSP_OFF_MISC + 2)[0] != 0


def test_build_dsp_state_seeds_default_noise_lfsr_without_active_noise_voice():
    a01 = bytearray(0xF8)
    a01[A01_OFF_KEYED] = 0x01
    a01[A01_OFF_DSP_REGS + DSP_REG_DIR] = 0x00
    ssz = bytearray(1281)
    base = SSZ_VOICE_BASE
    ext = SSZ_EXT_BASE
    ssz[base:base + 4] = (3).to_bytes(4, "big")
    ssz[ext + SSZ_EXT_ENV:ext + SSZ_EXT_ENV + 4] = (0x600).to_bytes(4, "big")
    ssz[ext + SSZ_EXT_OUT_SAMPLE:ext + SSZ_EXT_OUT_SAMPLE + 2] = (
        (0x1000).to_bytes(2, "big", signed=True)
    )

    dsp = _build_dsp_state(bytes(a01), bytearray(SR16_AR1_SIZE), bytes(ssz))

    assert struct.unpack_from("<H", dsp, DSP_OFF_MISC + 2)[0] == 0x4000


# ---------------------------------------------------------------------------
# Assemble
# ---------------------------------------------------------------------------

def test_assemble_snd_size_and_layout():
    ram = b"\xab" * SR16_AR1_SIZE
    smp = b"\xcd" * SND_SMP_BYTES
    dsp = b"\xef" * SND_DSP_BYTES
    cpu_to_smp = b"\x01\x02\x03\x04"
    snd = _assemble_snd(ram, smp, dsp, cpu_to_smp)
    assert len(snd) == SNES_SND_SIZE
    # Tail starts at SR16_AR1_SIZE + SMP + DSP. Last 4 bytes of the 16B tail
    # are the CPU->SMP ports.
    tail_start = SR16_AR1_SIZE + SND_SMP_BYTES + SND_DSP_BYTES
    tail = snd[tail_start:tail_start + SND_TAIL_BYTES]
    assert tail[12:16] == cpu_to_smp
    # Padding after tail is zeros
    after_tail = tail_start + SND_TAIL_BYTES
    assert snd[after_tail:] == b"\x00" * (SNES_SND_SIZE - after_tail)


def test_old_spc_safe_snd_preserves_ram_and_uses_valid_dsp_fallback():
    old = b"\x5a" * SR16_AR1_SIZE + b"\xff" * 256

    snd = _build_old_spc_safe_snd(old)

    assert len(snd) == SNES_SND_SIZE
    assert snd[:16] == b"\x5a" * 16
    assert _old_spc_dsp_state_plausible(
        snd[SR16_AR1_SIZE + SND_SMP_BYTES:SR16_AR1_SIZE + SND_SMP_BYTES + SND_DSP_BYTES]
    )


def test_old_spc_safe_snd_seeds_visible_active_voice_from_dsp_regs():
    old = bytearray(b"\x00" * (SR16_AR1_SIZE + 44 + 128))
    old[0x2000:0x2002] = (0x3456).to_bytes(2, "little")
    dsp_regs = SR16_AR1_SIZE + 44
    voice = 6
    reg = dsp_regs + voice * 0x10
    old[dsp_regs + DSP_REG_DIR] = 0x20
    old[reg + 0x00] = 0x3E
    old[reg + 0x01] = 0x3A
    old[reg + 0x04] = 0x00
    old[reg + 0x08] = 0x7F

    snd = _build_old_spc_safe_snd(bytes(old))
    dsp = snd[SR16_AR1_SIZE + SND_SMP_BYTES:SR16_AR1_SIZE + SND_SMP_BYTES + SND_DSP_BYTES]
    voice_off = DSP_OFF_VOICES + voice * DSP_VOICE_STRIDE

    assert int.from_bytes(dsp[voice_off + VOICE_OFF_ENV:voice_off + VOICE_OFF_ENV + 2], "little") == 0x7F0
    assert int.from_bytes(dsp[voice_off + VOICE_OFF_BRR_ADDR:voice_off + VOICE_OFF_BRR_ADDR + 2], "little") == 0x3456
    assert dsp[voice_off + VOICE_OFF_BRR_OFFSET] == 1
    assert dsp[voice_off + VOICE_OFF_T_ENVX_OUT] == 0x7F


def test_old_spc_dsp_plausibility_rejects_shifted_voice_payloads():
    dsp = bytearray(SND_DSP_BYTES)
    voice = DSP_OFF_VOICES
    dsp[voice + VOICE_OFF_ENV:voice + VOICE_OFF_ENV + 2] = (0xFFFF).to_bytes(2, "little")
    dsp[voice + VOICE_OFF_BRR_OFFSET] = 0xFE

    assert not _old_spc_dsp_state_plausible(bytes(dsp))
def test_default_ctl_matches_snes9x_idle_joypad_snapshot():
    ctl = _default_ctl()
    assert len(ctl) == 91
    assert ctl[0] == 4
    assert ctl[1] == 0x10
    assert ctl[7] == 0x10
    assert ctl[52] == 1
    assert ctl[63] == 1
