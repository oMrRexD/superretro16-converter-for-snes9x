"""Legacy SR16 SPC chunk conversion path."""
from __future__ import annotations

import struct

from converter.common.constants import (
    SNES_SND_SIZE, SR16_AR1_SIZE,
    SND_SMP_BYTES, SND_DSP_BYTES, SND_TAIL_BYTES,
    DSP_OFF_VOICES, DSP_VOICE_STRIDE, DSP_OFF_EXTERNAL_REGS,
    VOICE_OFF_INTERP_POS, VOICE_OFF_BRR_ADDR,
    VOICE_OFF_ENV, VOICE_OFF_HIDDEN_ENV, VOICE_OFF_BUF_POS,
    VOICE_OFF_BRR_OFFSET, VOICE_OFF_KON_DELAY, VOICE_OFF_ENV_MODE,
    VOICE_OFF_T_ENVX_OUT,
    DSP_OFF_MISC, DSP_MISC_ENVX_BUF, DSP_MISC_OUTX_BUF, DSP_MISC_NEW_KON,
    DSP_MISC_T_PMON, DSP_MISC_T_NON, DSP_MISC_T_EON,
    DSP_MISC_T_DIR, DSP_MISC_T_ESA, DSP_MISC_T_ECHO_EN,
    DSP_REG_PMON, DSP_REG_NON, DSP_REG_DIR, DSP_REG_FLG,
    DSP_REG_ESA, DSP_REG_EON,
)
from .snd_assembly import _assemble_snd
from .snd_binary import _pack_le_i16, _pack_le_i32, _pack_le_u16
from .snd_dsp import _build_ipl_boot_dsp_state
from .snd_smp import _smp_status_value

def _convert_old_spc_to_snd(old: bytes) -> bytes | None:
    """Convert SR16/old-snes9x Blargg SPC snapshot to current SND layout."""
    if len(old) < SR16_AR1_SIZE + 16 + 16 + 7 + 1 + 4:
        return None

    pos = 0
    ram = bytearray(old[pos:pos + SR16_AR1_SIZE])
    pos += SR16_AR1_SIZE
    regs = old[pos:pos + 16]
    pos += 16
    regs_in = old[pos:pos + 16]
    pos += 16
    if len(regs) != 16 or len(regs_in) != 16 or pos + 7 > len(old):
        return None

    pc = int.from_bytes(old[pos:pos + 2], "little")
    pos += 2
    spc_a = old[pos]
    spc_x = old[pos + 1]
    spc_y = old[pos + 2]
    psw = old[pos + 3]
    sp = old[pos + 4]
    pos += 5
    pos = _skip_old_spc_extra(old, pos)
    if pos is None or pos + 4 > len(old):
        return None

    spc_time = int.from_bytes(old[pos:pos + 2], "little")
    dsp_time = int.from_bytes(old[pos + 2:pos + 4], "little")
    pos += 4

    dsp_state, pos = _copy_old_spc_dsp_state(old, pos)
    if dsp_state is None:
        return None
    if not _old_spc_dsp_state_plausible(dsp_state):
        return None

    timers = []
    for _ in range(3):
        if pos + 4 > len(old):
            return None
        next_time = int.from_bytes(old[pos:pos + 2], "little")
        divider = old[pos + 2]
        counter = old[pos + 3]
        pos += 4
        pos = _skip_old_spc_extra(old, pos)
        if pos is None:
            return None
        timers.append((next_time, divider, counter))
    pos = _skip_old_spc_extra(old, pos)
    if pos is None:
        return None

    smp = bytearray(SND_SMP_BYTES)
    _pack_le_i32(smp, 0,  0)        # keep scheduler relative clock safe on load
    _pack_le_i32(smp, 4,  0)
    _pack_le_i32(smp, 8,  0)
    _pack_le_i32(smp, 12, pc)
    _pack_le_i32(smp, 16, sp)
    _pack_le_i32(smp, 20, spc_a)
    _pack_le_i32(smp, 24, spc_x)
    _pack_le_i32(smp, 28, spc_y)
    _pack_le_i32(smp, 32, 1 if psw & 0x80 else 0)
    _pack_le_i32(smp, 36, 1 if psw & 0x40 else 0)
    _pack_le_i32(smp, 40, 1 if psw & 0x20 else 0)
    _pack_le_i32(smp, 44, 1 if psw & 0x10 else 0)
    _pack_le_i32(smp, 48, 1 if psw & 0x08 else 0)
    _pack_le_i32(smp, 52, 1 if psw & 0x04 else 0)
    _pack_le_i32(smp, 56, 1 if psw & 0x02 else 0)
    _pack_le_i32(smp, 60, 1 if psw & 0x01 else 0)
    _pack_le_i32(smp, 64, regs[1] & 0x80)
    _pack_le_i32(smp, 68, regs[2])
    _pack_le_i32(smp, 72, _smp_status_value(regs_in[8]))
    _pack_le_i32(smp, 76, _smp_status_value(regs_in[9]))
    for i, (_next_time, divider, counter) in enumerate(timers):
        base = (20 + i * 5) * 4
        _pack_le_i32(smp, base,      1 if (regs[1] >> i) & 1 else 0)
        _pack_le_i32(smp, base + 4,  ((regs[10 + i] - 1) & 0xFF) + 1)
        _pack_le_i32(smp, base + 8,  divider)
        _pack_le_i32(smp, base + 12, divider)
        _pack_le_i32(smp, base + 16, counter)
    _pack_le_i32(smp, 35 * 4, 0)
    _pack_le_i32(smp, 36 * 4, 0)
    _pack_le_i32(smp, 37 * 4, 0)
    _pack_le_i32(smp, 38 * 4, sp)
    _pack_le_i32(smp, 39 * 4, (spc_y << 8) | spc_a)
    _pack_le_i32(smp, 40 * 4, 0)

    tail = bytearray(SND_TAIL_BYTES)
    # reference_time, remainder, dsp.clock all stay 0
    tail[12:16] = regs_in[4:8]                  # CPU/APU ports

    body = bytes(ram) + bytes(smp) + dsp_state + bytes(tail)
    return body + (b"\x00" * (SNES_SND_SIZE - len(body)))

def _build_old_spc_safe_snd(old: bytes) -> bytes:
    """Fallback for old SPC blobs whose DSP pipeline is not current-compatible.

    Some SR16 saves carry a larger legacy SPC blob with old Blargg extra/pointer
    fields that cannot be trusted by current snes9x's DSP loader. Preserve SPC
    RAM, SPC700 registers, timers, DSP registers, and CPU/APU ports, but reset
    the hidden DSP voice pipeline to a deterministic shape instead of restoring
    malformed internal voice pointers.
    """
    if len(old) < SR16_AR1_SIZE + 44 + 128:
        ram = old[:SR16_AR1_SIZE].ljust(SR16_AR1_SIZE, b"\x00")
        body = ram + bytes(SND_SMP_BYTES) + _build_ipl_boot_dsp_state() + bytes(SND_TAIL_BYTES)
        return body + b"\x00" * (SNES_SND_SIZE - len(body))

    pos = SR16_AR1_SIZE
    ram = bytearray(old[:SR16_AR1_SIZE])
    regs = old[pos:pos + 16]
    regs_in = old[pos + 16:pos + 32]
    pc = int.from_bytes(old[pos + 32:pos + 34], "little")
    spc_a = old[pos + 34]
    spc_x = old[pos + 35]
    spc_y = old[pos + 36]
    psw = old[pos + 37]
    sp = old[pos + 38]
    dsp_regs = bytearray(old[pos + 44:pos + 44 + 128])

    smp = bytearray(SND_SMP_BYTES)
    _pack_le_i32(smp, 0, 0)
    _pack_le_i32(smp, 3 * 4, pc)
    _pack_le_i32(smp, 4 * 4, sp)
    _pack_le_i32(smp, 5 * 4, spc_a)
    _pack_le_i32(smp, 6 * 4, spc_x)
    _pack_le_i32(smp, 7 * 4, spc_y)
    for idx, bit in enumerate((0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01), start=8):
        _pack_le_i32(smp, idx * 4, 1 if psw & bit else 0)
    _pack_le_i32(smp, 16 * 4, regs[1] & 0x80)
    _pack_le_i32(smp, 17 * 4, regs[2])
    _pack_le_i32(smp, 18 * 4, _smp_status_value(regs_in[8]))
    _pack_le_i32(smp, 19 * 4, _smp_status_value(regs_in[9]))
    for i in range(3):
        base = (20 + i * 5) * 4
        _pack_le_i32(smp, base, 1 if ((regs[1] >> i) & 1) else 0)
        _pack_le_i32(smp, base + 4, ((regs[10 + i] - 1) & 0xFF) + 1)
    _pack_le_i32(smp, 38 * 4, sp)
    _pack_le_i32(smp, 39 * 4, (spc_y << 8) | spc_a)

    dsp = bytearray(_build_ipl_boot_dsp_state())
    dsp[0:128] = dsp_regs
    dsp[DSP_OFF_EXTERNAL_REGS:DSP_OFF_EXTERNAL_REGS + 128] = dsp_regs
    dsp[DSP_MISC_T_PMON] = dsp_regs[DSP_REG_PMON]
    dsp[DSP_MISC_T_NON] = dsp_regs[DSP_REG_NON]
    dsp[DSP_MISC_T_EON] = dsp_regs[DSP_REG_EON]
    dsp[DSP_MISC_T_DIR] = dsp_regs[DSP_REG_DIR]
    dsp[DSP_MISC_T_ESA] = dsp_regs[DSP_REG_ESA]
    dsp[DSP_MISC_T_ECHO_EN] = dsp_regs[DSP_REG_FLG]
    dsp[DSP_MISC_NEW_KON] = 0
    _seed_legacy_spc_visible_voices(dsp, dsp_regs, ram)

    return _assemble_snd(bytes(ram), bytes(smp), bytes(dsp), regs_in[4:8])

def _seed_legacy_spc_visible_voices(
    dsp: bytearray,
    dsp_regs: bytearray,
    ram: bytearray,
) -> int:
    """Resume audible voices in old `SPC:68608` fallback snapshots.

    The legacy Top Gear 3000 save carries trustworthy DSP registers but its
    hidden Blargg voice payload is not current-snes9x compatible. Resetting the
    whole hidden voice pipeline keeps the save stable, but voices that the
    driver expects to be already sustaining (notably the car engine) stay silent
    until the driver re-keys them. Use visible ENVX/OUTX + source-directory
    pointers as a conservative approximation of the missing pipeline.
    """
    resumed = 0
    envx_buf = 0
    outx_buf = 0
    if len(dsp) < SND_DSP_BYTES or len(dsp_regs) < 128:
        return resumed

    dir_base = (dsp_regs[DSP_REG_DIR] << 8) & 0xFFFF
    for voice in range(8):
        reg_off = voice * 0x10
        envx = dsp_regs[reg_off + 0x08]
        volume = abs(dsp_regs[reg_off]) + abs(dsp_regs[reg_off + 0x01])
        if envx == 0 or volume == 0:
            continue

        srcn = dsp_regs[reg_off + 0x04]
        dir_addr = (dir_base + srcn * 4) & 0xFFFF
        if dir_addr + 4 > len(ram):
            continue
        sample_start = int.from_bytes(ram[dir_addr:dir_addr + 2], "little")
        if sample_start >= len(ram):
            continue

        voice_off = DSP_OFF_VOICES + voice * DSP_VOICE_STRIDE
        env = min(0x7FF, max(1, envx << 4))
        _pack_le_u16(dsp, voice_off + VOICE_OFF_INTERP_POS, 0x4000)
        _pack_le_u16(dsp, voice_off + VOICE_OFF_BRR_ADDR, sample_start)
        _pack_le_u16(dsp, voice_off + VOICE_OFF_ENV, env)
        _pack_le_i16(dsp, voice_off + VOICE_OFF_HIDDEN_ENV, env)
        dsp[voice_off + VOICE_OFF_BUF_POS] = 0
        dsp[voice_off + VOICE_OFF_BRR_OFFSET] = 1
        dsp[voice_off + VOICE_OFF_KON_DELAY] = 0
        dsp[voice_off + VOICE_OFF_ENV_MODE] = 3
        dsp[voice_off + VOICE_OFF_T_ENVX_OUT] = envx
        envx_buf = envx
        outx_buf = dsp_regs[reg_off + 0x09]
        resumed |= 1 << voice

    if resumed:
        dsp[DSP_MISC_ENVX_BUF] = envx_buf
        dsp[DSP_MISC_OUTX_BUF] = outx_buf
    return resumed

def _old_spc_dsp_state_plausible(dsp: bytes) -> bool:
    """Reject old-SPC DSP states that decode into impossible voice fields."""
    if len(dsp) != SND_DSP_BYTES:
        return False
    impossible = 0
    for voice in range(8):
        off = DSP_OFF_VOICES + voice * DSP_VOICE_STRIDE
        env = int.from_bytes(dsp[off + VOICE_OFF_ENV:off + VOICE_OFF_ENV + 2], "little")
        hidden_env = struct.unpack_from("<h", dsp, off + VOICE_OFF_HIDDEN_ENV)[0]
        brr_offset = dsp[off + VOICE_OFF_BRR_OFFSET]
        env_mode = dsp[off + VOICE_OFF_ENV_MODE]
        if env > 0x7FF or hidden_env < -0x800 or hidden_env > 0x7FF:
            impossible += 1
        if brr_offset > 12 or env_mode > 4:
            impossible += 1
    return impossible == 0

def _skip_old_spc_extra(old: bytes, pos: int) -> int | None:
    if pos >= len(old):
        return None
    extra = old[pos]
    pos += 1 + extra
    if pos > len(old):
        return None
    return pos

def _copy_old_spc_dsp_state(old: bytes, pos: int) -> tuple[bytes | None, int]:
    """Copy Blargg DSP state while skipping old variable-length extras.

    Older SPC_DSP snapshots insert an ``extra`` block after each voice and at
    the end of the DSP payload. Those bytes are not part of current snes9x's
    fixed 642-byte DSP state; copying them verbatim shifts later voice/misc
    fields and can leave bogus BRR pointers that crash the audio core.
    """
    out = bytearray()
    if pos + 128 > len(old):
        return None, pos
    out += old[pos:pos + 128]
    pos += 128
    for _ in range(8):
        if pos + 37 > len(old):
            return None, pos
        out += old[pos:pos + 37]
        out += b"\x00"  # current voice stride is 38 bytes
        pos += 37
        next_pos = _skip_old_spc_extra(old, pos)
        if next_pos is None:
            return None, pos
        pos = next_pos
    if pos + 32 + 49 + 128 > len(old):
        return None, pos
    out += old[pos:pos + 32 + 49 + 128]
    pos += 32 + 49 + 128
    next_pos = _skip_old_spc_extra(old, pos)
    if next_pos is None:
        return None, pos
    pos = next_pos

    if len(out) < SND_DSP_BYTES:
        out += b"\x00" * (SND_DSP_BYTES - len(out))
    elif len(out) > SND_DSP_BYTES:
        del out[SND_DSP_BYTES:]
    return bytes(out), pos
