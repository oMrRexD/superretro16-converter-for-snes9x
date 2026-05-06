"""snes9x SND -> SR16 A01, AR1, and SSZ audio sections."""
from __future__ import annotations

import struct

from converter.common.constants import (
    SR16_A01_SIZE, SR16_AR1_SIZE, SR16_SSZ_SIZE, SNES_SND_SIZE,
    SND_OFF_SPC_RAM, SND_OFF_SMP, SND_SMP_BYTES,
    SND_OFF_DSP, SND_DSP_BYTES, SND_OFF_TAIL, SND_TAIL_CPU_PORTS_REL,
    SMP_FIELD_PC, SMP_FIELD_SP, SMP_FIELD_A, SMP_FIELD_X, SMP_FIELD_Y,
    SMP_FIELD_PSW_BASE, SMP_FIELD_IPL_ROM,
    SMP_FIELD_TIMER_BASE, SMP_TIMER_STRIDE_FIELDS,
    SMP_TIMER_FIELD_ENABLE, SMP_TIMER_FIELD_TARGET, SMP_TIMER_FIELD_STAGE3,
    DSP_REG_MVOL_L, DSP_REG_MVOL_R, DSP_REG_EVOL_L, DSP_REG_EVOL_R,
    DSP_REG_EON, DSP_REG_EFB, DSP_REG_FLG, DSP_REG_PMON,
    DSP_REG_VOICE_STRIDE, DSP_VREG_VOL_L, DSP_VREG_VOL_R,
    DSP_VREG_PITCH_L, DSP_VREG_PITCH_H, DSP_VREG_ADSR1, DSP_VREG_ADSR2,
    DSP_OFF_VOICES, DSP_VOICE_STRIDE, DSP_MISC_KON,
    DSP_MISC_ECHO_OFFSET, DSP_MISC_ECHO_LENGTH,
    VOICE_OFF_BUF12, VOICE_OFF_INTERP_POS, VOICE_OFF_BRR_ADDR,
    VOICE_OFF_ENV, VOICE_OFF_BRR_OFFSET, VOICE_OFF_ENV_MODE,
    VOICE_OFF_T_ENVX_OUT,
    A01_OFF_WAIT_COUNTER, A01_OFF_Y, A01_OFF_A, A01_OFF_X, A01_OFF_SP,
    A01_OFF_PSW, A01_OFF_CYCLES, A01_OFF_PC,
    A01_OFF_IPL_ROM, A01_OFF_KEYED, A01_OFF_OUT_PORTS,
    A01_OFF_TIMER, A01_OFF_TIMER_TARGET, A01_OFF_TIMER_ENABLED,
    A01_OFF_DSP_REGS, A01_OFF_EXTRA_RAM, A01_TIMER_COUNT,
    A01_EXTRA_RAM_SIZE,
    SPC_PORT_F4, SPC_PORT_COUNT,
    SSZ_VOICE_BASE, SSZ_VOICE_STRIDE,
    SSZ_VOICE_SAMPLE_MODE, SSZ_VOICE_LOOP_FLAG,
    SSZ_VOICE_VOL_L, SSZ_VOICE_VOL_R, SSZ_VOICE_PITCH, SSZ_VOICE_ENV,
    SSZ_VOICE_LOOP, SSZ_VOICE_ATTACK_RATE, SSZ_VOICE_DECAY_RATE,
    SSZ_VOICE_SUSTAIN_RATE, SSZ_VOICE_GAIN,
    SSZ_VOICE_DECODED, SSZ_VOICE_BLOCK_PTR, SSZ_VOICE_SAMPLE_PTR,
    SSZ_EXT_BASE, SSZ_EXT_STRIDE, SSZ_EXT_OUT_SAMPLE, SSZ_EXT_ENV,
    SSZ_OFF_ECHO_OFFSET, SSZ_OFF_ECHO_LENGTH,
)


_PSW_FLAG_MASKS = (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01)
_ENV_MODE_TO_SR16_SAMPLE_MODE = {0: 0, 1: 1, 2: 2, 3: 3, 4: 5}
_DSP_SAVED_BUFFER_SAMPLES = 12
_SSZ_DECODED_SAMPLE_COUNT = 16
_SNES_PITCH_UNITS = 4096
_SR16_PITCH_UNITS = 32000


def _le_i32(buf: bytes, off: int) -> int:
    return struct.unpack_from("<i", buf, off)[0]


def _le_u16(buf: bytes, off: int) -> int:
    return struct.unpack_from("<H", buf, off)[0]


def _le_i16(buf: bytes, off: int) -> int:
    return struct.unpack_from("<h", buf, off)[0]


def _smp_i32(smp: bytes, field_index: int) -> int:
    return _le_i32(smp, field_index * 4)


def _smp_timer_field(timer: int, field: int) -> int:
    return (SMP_FIELD_TIMER_BASE + timer * SMP_TIMER_STRIDE_FIELDS + field) * 4


def _put_be(out: bytearray, off: int, val: int, size: int) -> None:
    mask = (1 << (size * 8)) - 1
    out[off:off + size] = (val & mask).to_bytes(size, "big")


def _put_be_s16(out: bytearray, off: int, val: int) -> None:
    val = max(-32768, min(32767, int(val)))
    out[off:off + 2] = val.to_bytes(2, "big", signed=True)


def _s8(v: int) -> int:
    return v - 256 if v & 0x80 else v


def _psw_from_smp_flags(smp: bytes) -> int:
    psw = 0
    for bit, mask in enumerate(_PSW_FLAG_MASKS):
        if _smp_i32(smp, SMP_FIELD_PSW_BASE + bit):
            psw |= mask
    return psw


def _active_voice_key_mask(dsp_block: bytes) -> int:
    keyed = dsp_block[DSP_MISC_KON] if len(dsp_block) > DSP_MISC_KON else 0
    for voice in range(8):
        voff = DSP_OFF_VOICES + voice * DSP_VOICE_STRIDE
        if voff + VOICE_OFF_ENV + 2 <= len(dsp_block):
            env_mode = dsp_block[voff + VOICE_OFF_ENV_MODE]
            env = _le_u16(dsp_block, voff + VOICE_OFF_ENV)
            if env_mode > 0 and env > 0:
                keyed |= 1 << voice
    return keyed & 0xFF


def _write_a01_timers(out: bytearray, smp: bytes) -> None:
    for timer in range(A01_TIMER_COUNT):
        stage3_off = _smp_timer_field(timer, SMP_TIMER_FIELD_STAGE3)
        target_off = _smp_timer_field(timer, SMP_TIMER_FIELD_TARGET)
        enable_off = _smp_timer_field(timer, SMP_TIMER_FIELD_ENABLE)
        _put_be(out, A01_OFF_TIMER + timer * 2, _le_i32(smp, stage3_off), 2)
        _put_be(out, A01_OFF_TIMER_TARGET + timer * 2, _le_i32(smp, target_off), 2)
        out[A01_OFF_TIMER_ENABLED + timer] = 1 if _le_i32(smp, enable_off) else 0


def build_a01(snd: bytes) -> bytes:
    """Build SR16 A01 (248B) from snes9x SND (66560B)."""
    if len(snd) < SNES_SND_SIZE:
        raise ValueError(f"SND chunk too small: {len(snd)}")

    smp = snd[SND_OFF_SMP:SND_OFF_SMP + SND_SMP_BYTES]
    dsp_block = snd[SND_OFF_DSP:SND_OFF_DSP + SND_DSP_BYTES]
    spc_ram = snd[SND_OFF_SPC_RAM:SND_OFF_SPC_RAM + SR16_AR1_SIZE]
    out = bytearray(SR16_A01_SIZE)

    out[A01_OFF_Y] = _smp_i32(smp, SMP_FIELD_Y) & 0xFF
    out[A01_OFF_A] = _smp_i32(smp, SMP_FIELD_A) & 0xFF
    out[A01_OFF_X] = _smp_i32(smp, SMP_FIELD_X) & 0xFF
    out[A01_OFF_SP] = _smp_i32(smp, SMP_FIELD_SP) & 0xFF
    out[A01_OFF_PSW] = _psw_from_smp_flags(smp)
    _put_be(out, A01_OFF_PC, _smp_i32(smp, SMP_FIELD_PC), 2)
    _put_be(out, A01_OFF_WAIT_COUNTER, 0, 4)
    _put_be(out, A01_OFF_CYCLES, 0, 4)
    out[A01_OFF_IPL_ROM] = 1 if _smp_i32(smp, SMP_FIELD_IPL_ROM) else 0
    out[A01_OFF_KEYED] = _active_voice_key_mask(dsp_block)
    out[A01_OFF_OUT_PORTS:A01_OFF_OUT_PORTS + SPC_PORT_COUNT] = (
        spc_ram[SPC_PORT_F4:SPC_PORT_F4 + SPC_PORT_COUNT]
    )
    _write_a01_timers(out, smp)
    out[A01_OFF_DSP_REGS:A01_OFF_DSP_REGS + DSP_OFF_VOICES] = (
        dsp_block[0:DSP_OFF_VOICES]
    )
    out[A01_OFF_EXTRA_RAM:A01_OFF_EXTRA_RAM + A01_EXTRA_RAM_SIZE] = (
        spc_ram[-A01_EXTRA_RAM_SIZE:]
    )
    return bytes(out)


def build_ar1(snd: bytes) -> bytes:
    """Build SR16 AR1 (64KB) from snes9x SND."""
    if len(snd) < SNES_SND_SIZE:
        raise ValueError(f"SND chunk too small: {len(snd)}")

    ar1 = bytearray(snd[SND_OFF_SPC_RAM:SND_OFF_SPC_RAM + SR16_AR1_SIZE])
    tail_off = SND_OFF_TAIL + SND_TAIL_CPU_PORTS_REL
    if len(snd) >= tail_off + SPC_PORT_COUNT:
        ar1[SPC_PORT_F4:SPC_PORT_F4 + SPC_PORT_COUNT] = (
            snd[tail_off:tail_off + SPC_PORT_COUNT]
        )
    return bytes(ar1)


def _write_ssz_header(out: bytearray, dr: bytes, dsp: bytes) -> None:
    _put_be(out, 0x0000, _s8(dr[DSP_REG_MVOL_L]) & 0xFFFF, 2)
    _put_be(out, 0x0002, _s8(dr[DSP_REG_MVOL_R]) & 0xFFFF, 2)
    _put_be(out, 0x0004, _s8(dr[DSP_REG_EVOL_L]) & 0xFFFF, 2)
    _put_be(out, 0x0006, _s8(dr[DSP_REG_EVOL_R]) & 0xFFFF, 2)
    _put_be(out, 0x0008, dr[DSP_REG_EON], 4)
    _put_be(out, 0x000C, _s8(dr[DSP_REG_EFB]) & 0xFFFFFFFF, 4)
    _put_be(out, SSZ_OFF_ECHO_OFFSET, _le_u16(dsp, DSP_MISC_ECHO_OFFSET), 4)
    _put_be(out, SSZ_OFF_ECHO_LENGTH, _le_u16(dsp, DSP_MISC_ECHO_LENGTH), 4)
    _put_be(out, 0x0018, 0 if (dr[DSP_REG_FLG] & 0x20) else 1, 4)
    _put_be(out, 0x0020, dr[DSP_REG_PMON], 4)


def _sr16_pitch_from_dsp_regs(dr: bytes, voice: int) -> int:
    base = voice * DSP_REG_VOICE_STRIDE
    pitch = dr[base + DSP_VREG_PITCH_L] | (dr[base + DSP_VREG_PITCH_H] << 8)
    return ((pitch & 0x3FFF) * _SR16_PITCH_UNITS) // _SNES_PITCH_UNITS


def _sr16_attack_rate_from_adsr1(adsr1: int) -> int:
    return ((adsr1 & 0x0F) * 2 + 1) if (adsr1 & 0x80) else 0


def _sr16_decay_rate_from_adsr1(adsr1: int) -> int:
    return ((adsr1 >> 4) & 0x07) * 2 + 0x10


def _sr16_gain_from_adsr2(adsr2: int) -> int:
    # Preserve the current SSZ synthesis mapping exactly; reverse-converted
    # saves are regression-tested at the byte/section level.
    return ((adsr2 >> 5) & (0x07 + 1)) << 8


def _write_ssz_voice(out: bytearray, dsp: bytes, dr: bytes, voice: int) -> None:
    voff = DSP_OFF_VOICES + voice * DSP_VOICE_STRIDE
    if voff + DSP_VOICE_STRIDE > len(dsp):
        return

    ssz_base = SSZ_VOICE_BASE + voice * SSZ_VOICE_STRIDE
    ext_base = SSZ_EXT_BASE + voice * SSZ_EXT_STRIDE
    reg_base = voice * DSP_REG_VOICE_STRIDE

    env = _le_u16(dsp, voff + VOICE_OFF_ENV)
    env_mode = dsp[voff + VOICE_OFF_ENV_MODE]
    block_addr = _le_u16(dsp, voff + VOICE_OFF_BRR_ADDR)
    brr_offset = dsp[voff + VOICE_OFF_BRR_OFFSET]
    interp_pos = _le_u16(dsp, voff + VOICE_OFF_INTERP_POS)

    _put_be(
        out,
        ssz_base + SSZ_VOICE_SAMPLE_MODE,
        _ENV_MODE_TO_SR16_SAMPLE_MODE.get(env_mode, 0),
        4,
    )
    _put_be(out, ssz_base + SSZ_VOICE_LOOP_FLAG, 0, 4)
    _put_be(out, ssz_base + SSZ_VOICE_VOL_L,
            _s8(dr[reg_base + DSP_VREG_VOL_L]) & 0xFFFF, 2)
    _put_be(out, ssz_base + SSZ_VOICE_VOL_R,
            _s8(dr[reg_base + DSP_VREG_VOL_R]) & 0xFFFF, 2)
    _put_be(out, ssz_base + SSZ_VOICE_PITCH,
            _sr16_pitch_from_dsp_regs(dr, voice), 4)
    _put_be(out, ssz_base + SSZ_VOICE_ENV, env << 4, 4)
    _put_be(out, ext_base + SSZ_EXT_ENV, env, 4)

    for i in range(_DSP_SAVED_BUFFER_SAMPLES):
        sample = _le_i16(dsp, voff + VOICE_OFF_BUF12 + i * 2)
        _put_be_s16(out, ssz_base + SSZ_VOICE_DECODED + i * 2, sample)
    for i in range(_DSP_SAVED_BUFFER_SAMPLES, _SSZ_DECODED_SAMPLE_COUNT):
        _put_be_s16(out, ssz_base + SSZ_VOICE_DECODED + i * 2, 0)

    _put_be(out, ssz_base + SSZ_VOICE_BLOCK_PTR, block_addr, 4)
    sample_ptr = (brr_offset * 4 + (interp_pos >> 12)) & 0xFFFF
    _put_be(out, ssz_base + SSZ_VOICE_SAMPLE_PTR, sample_ptr, 4)

    envx_out = dsp[voff + VOICE_OFF_T_ENVX_OUT]
    if env > 0 and envx_out > 0:
        last_sample = _le_i16(
            dsp,
            voff + VOICE_OFF_BUF12 + (_DSP_SAVED_BUFFER_SAMPLES - 1) * 2,
        )
        out_sample = (last_sample * env) >> 11
    else:
        out_sample = 0
    _put_be_s16(out, ext_base + SSZ_EXT_OUT_SAMPLE, out_sample)

    adsr1 = dr[reg_base + DSP_VREG_ADSR1]
    adsr2 = dr[reg_base + DSP_VREG_ADSR2]
    _put_be(out, ssz_base + SSZ_VOICE_ATTACK_RATE,
            _sr16_attack_rate_from_adsr1(adsr1), 4)
    _put_be(out, ssz_base + SSZ_VOICE_DECAY_RATE,
            _sr16_decay_rate_from_adsr1(adsr1), 4)
    _put_be(out, ssz_base + SSZ_VOICE_SUSTAIN_RATE, adsr2 & 0x1F, 4)
    _put_be(out, ssz_base + SSZ_VOICE_GAIN, _sr16_gain_from_adsr2(adsr2), 4)
    _put_be(out, ssz_base + SSZ_VOICE_LOOP,
            0 if env_mode in (0, 1, 3) else 1, 4)


def build_ssz(snd: bytes) -> bytes:
    """Build SR16 SSZ (1281B) from Blargg DSP state."""
    if len(snd) < SNES_SND_SIZE:
        raise ValueError(f"SND chunk too small: {len(snd)}")

    dsp = snd[SND_OFF_DSP:SND_OFF_DSP + SND_DSP_BYTES]
    dr = dsp[0:DSP_OFF_VOICES]
    out = bytearray(SR16_SSZ_SIZE)
    _write_ssz_header(out, dr, dsp)
    for voice in range(8):
        _write_ssz_voice(out, dsp, dr, voice)
    return bytes(out)
