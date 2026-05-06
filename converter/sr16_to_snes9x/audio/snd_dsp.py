"""DSP state reconstruction and SSZ voice seeding for snes9x SND chunks."""
from __future__ import annotations

from converter.common.constants import (
    SR16_SSZ_SIZE, SND_DSP_BYTES,
    DSP_OFF_VOICES, DSP_VOICE_STRIDE, DSP_OFF_EXTERNAL_REGS,
    VOICE_OFF_BUF12, VOICE_OFF_INTERP_POS, VOICE_OFF_BRR_ADDR,
    VOICE_OFF_ENV, VOICE_OFF_HIDDEN_ENV, VOICE_OFF_BUF_POS,
    VOICE_OFF_BRR_OFFSET, VOICE_OFF_KON_DELAY, VOICE_OFF_ENV_MODE,
    VOICE_OFF_T_ENVX_OUT,
    DSP_OFF_MISC,
    DSP_MISC_KON, DSP_MISC_NEW_KON, DSP_MISC_ENDX_BUF,
    DSP_MISC_ENVX_BUF, DSP_MISC_OUTX_BUF,
    DSP_MISC_ECHO_OFFSET, DSP_MISC_ECHO_LENGTH,
    DSP_MISC_T_PMON, DSP_MISC_T_NON, DSP_MISC_T_EON,
    DSP_MISC_T_DIR, DSP_MISC_T_KOFF, DSP_MISC_T_ESA, DSP_MISC_T_ECHO_EN,
    DSP_REG_NON, DSP_REG_DIR, DSP_REG_FLG, DSP_REG_ESA, DSP_REG_ENDX,
    DSP_REG_PMON, DSP_REG_EON,
    A01_OFF_KEYED, A01_OFF_DSP_REGS, A01_OFF_EXTRA_RAM,
    SSZ_VOICE_BASE, SSZ_VOICE_STRIDE,
    SSZ_VOICE_OLD_ENV, SSZ_VOICE_DECODED,
    SSZ_VOICE_PREV1, SSZ_VOICE_PREV2,
    SSZ_VOICE_BLOCK_PTR, SSZ_VOICE_SAMPLE_PTR,
    SSZ_EXT_BASE, SSZ_EXT_STRIDE, SSZ_EXT_OUT_SAMPLE, SSZ_EXT_ENV,
    SSZ_OFF_ECHO_OFFSET, SSZ_OFF_ECHO_LENGTH,
)
from .phase_calibration import _calibrate_ssz_voice_window
from .snd_binary import _be_s16, _be_u, _pack_le_i16, _pack_le_u16
from .voice_policy import (
    _clear_initial_echo_buffer,
    _quiet_duplicate_ssz_voice_mask,
    _s8,
    _should_resume_ssz_voice,
)

_DSP_POWERON_EXTERNAL_REGS = bytes([
    0x45, 0x8B, 0x5A, 0x9A, 0xE4, 0x82, 0x1B, 0x78,
    0x00, 0x00, 0xAA, 0x96, 0x89, 0x0E, 0xE0, 0x80,
    0x2A, 0x49, 0x3D, 0xBA, 0x14, 0xA0, 0xAC, 0xC5,
    0x00, 0x00, 0x51, 0xBB, 0x9C, 0x4E, 0x7B, 0xFF,
    0xF4, 0xFD, 0x57, 0x32, 0x37, 0xD9, 0x42, 0x22,
    0x00, 0x00, 0x5B, 0x3C, 0x9F, 0x1B, 0x87, 0x9A,
    0x6F, 0x27, 0xAF, 0x7B, 0xE5, 0x68, 0x0A, 0xD9,
    0x00, 0x00, 0x9A, 0xC5, 0x9C, 0x4E, 0x7B, 0xFF,
    0xEA, 0x21, 0x78, 0x4F, 0xDD, 0xED, 0x24, 0x14,
    0x00, 0x00, 0x77, 0xB1, 0xD1, 0x36, 0xC1, 0x67,
    0x52, 0x57, 0x46, 0x3D, 0x59, 0xF4, 0x87, 0xA4,
    0x00, 0x00, 0x7E, 0x44, 0x00, 0x4E, 0x7B, 0xFF,
    0x75, 0xF5, 0x06, 0x97, 0x10, 0xC3, 0x24, 0xBB,
    0x00, 0x00, 0x7B, 0x7A, 0xE0, 0x60, 0x12, 0x0F,
    0xF7, 0x74, 0x1C, 0xE5, 0x39, 0x3D, 0x73, 0xC1,
    0x00, 0x00, 0x7A, 0xB3, 0xFF, 0x4E, 0x7B, 0xFF,
])


# ---------------------------------------------------------------------------
# Small endian helpers (lifted out of nested closures for testability)
# ---------------------------------------------------------------------------

def _u8_from_signed_high(value: int) -> int:
    """Return the high byte snes9x exposes through signed OUTX-style fields."""
    return (int(value) >> 8) & 0xFF

def _derive_noise_seed(saved_out_sample: int, env: int) -> int:
    """Approximate Blargg's noise LFSR from old SoundData output + envelope.

    For noise voices, SPC_DSP replaces BRR interpolation with
    ``(int16_t)(m.noise * 2)`` and then applies the envelope. SSZ does not carry
    Blargg's LFSR directly, but it does carry the post-envelope voice output.
    This seed makes the first restored noise sample agree with the saved output
    instead of starting from silence/default noise.
    """
    if env <= 0:
        return 0x4000
    pre_env = int(round((int(saved_out_sample) << 11) / env))
    return (pre_env // 2) & 0xFFFF


# ---------------------------------------------------------------------------
# Mailbox handling
# ---------------------------------------------------------------------------

def _seed_voices_from_ssz(dsp: bytearray, dsp_regs: bytearray,
                          ssz: bytes, ram: bytearray,
                          keyed: int) -> tuple[int, int, int, int | None]:
    """Translate SSZ's old SoundData per-voice state into Blargg DSP voices.

    Mutates ``dsp`` and ``dsp_regs`` (writing voice + visible ENVX/OUTX
    mirrors). Returns ``(resumed_keyed, envx_buf, outx_buf, noise_seed)``.
    """
    resumed_keyed = 0
    envx_buf = 0
    outx_buf = 0
    noise_seed: int | None = None
    quiet_duplicate_mask = _quiet_duplicate_ssz_voice_mask(ssz, dsp_regs, keyed)
    active_meta: list[dict[str, int | bool]] = []
    ended_by_srcn: dict[int, int] = {}
    active_count_by_srcn: dict[int, int] = {}
    for voice in range(8):
        base = SSZ_VOICE_BASE + voice * SSZ_VOICE_STRIDE
        ext = SSZ_EXT_BASE + voice * SSZ_EXT_STRIDE
        state = _be_u(ssz, base + 0x00, 4)
        old_env = _be_u(ssz, ext + SSZ_EXT_ENV, 4)
        if old_env == 0:
            old_env = _be_u(ssz, base + SSZ_VOICE_OLD_ENV, 4) << 4
        env = max(0, min(0x7FF, old_env))
        active = state != 0 and bool(keyed & (1 << voice)) and env > 0
        srcn = dsp_regs[voice * 0x10 + 0x04]
        ended = bool(dsp_regs[DSP_REG_ENDX] & (1 << voice))
        if active:
            active_count_by_srcn[srcn] = active_count_by_srcn.get(srcn, 0) + 1
        if active and ended:
            ended_by_srcn[srcn] = ended_by_srcn.get(srcn, 0) + 1
        active_meta.append({
            "active": active,
            "srcn": srcn,
            "ended": ended,
            "moving": bool(
                _be_u(ssz, base + 0x23, 4) or _be_u(ssz, ext + 0x0E, 4)
            ),
        })

    for voice in range(8):
        base = SSZ_VOICE_BASE + voice * SSZ_VOICE_STRIDE
        ext = SSZ_EXT_BASE + voice * SSZ_EXT_STRIDE
        voice_off = DSP_OFF_VOICES + voice * DSP_VOICE_STRIDE

        state = _be_u(ssz, base + 0x00, 4)
        old_env = _be_u(ssz, ext + SSZ_EXT_ENV, 4)
        if old_env == 0:
            old_env = _be_u(ssz, base + SSZ_VOICE_OLD_ENV, 4) << 4
        env = max(0, min(0x7FF, old_env))
        active = state != 0 and bool(keyed & (1 << voice)) and env > 0
        uses_noise = bool(dsp_regs[DSP_REG_NON] & (1 << voice))
        resume_voice = _should_resume_ssz_voice(active, uses_noise)
        if quiet_duplicate_mask & (1 << voice):
            resume_voice = False
        if resume_voice:
            resumed_keyed |= 1 << voice

        decoded = [
            _be_s16(ssz, base + SSZ_VOICE_DECODED + i * 2) for i in range(16)
        ]
        sample_ptr = _be_u(ssz, base + SSZ_VOICE_SAMPLE_PTR, 4)
        out_sample = _be_s16(ssz, ext + SSZ_EXT_OUT_SAMPLE)
        block_ptr = _be_u(ssz, base + SSZ_VOICE_BLOCK_PTR, 4) & 0xFFFF
        srcn = dsp_regs[voice * 0x10 + 0x04]
        pitch = dsp_regs[voice * 0x10 + 0x02] | (dsp_regs[voice * 0x10 + 0x03] << 8)
        voice_volume_sum = abs(_s8(dsp_regs[voice * 0x10 + 0x00]))
        voice_volume_sum += abs(_s8(dsp_regs[voice * 0x10 + 0x01]))
        dir_addr = ((dsp_regs[DSP_REG_DIR] << 8) + srcn * 4) & 0xFFFF
        loop_ptr = int.from_bytes(ram[dir_addr + 2:dir_addr + 4], "little")
        prev_last2 = (
            _be_s16(ssz, base + SSZ_VOICE_PREV2),
            _be_s16(ssz, base + SSZ_VOICE_PREV1),
        )
        meta = active_meta[voice]
        _best_ptr, buf12, interp_pos, next_brr_addr, next_brr_offset = (
            _calibrate_ssz_voice_window(
                ram, block_ptr, loop_ptr, decoded, prev_last2,
                sample_ptr, out_sample, env if resume_voice else 0,
                voice_ended=bool(meta["ended"]),
                echo_enabled=bool(dsp_regs[DSP_REG_EON] & (1 << voice)),
                envelope_moving=bool(meta["moving"]),
                same_srcn_ended_peer=(
                    bool(dsp_regs[DSP_REG_EON] & (1 << voice))
                    and ended_by_srcn.get(int(meta["srcn"]), 0)
                    > (1 if meta["ended"] else 0)
                ),
                same_srcn_active_count=active_count_by_srcn.get(int(meta["srcn"]), 0),
                low_srcn_voice=srcn < 0x10,
                srcn=srcn,
                pitch=pitch,
                voice_volume_sum=voice_volume_sum,
            )
        )
        for i, sample in enumerate(buf12):
            _pack_le_i16(dsp, voice_off + VOICE_OFF_BUF12 + i * 2, sample)

        _pack_le_u16(dsp, voice_off + VOICE_OFF_INTERP_POS, interp_pos)
        _pack_le_u16(dsp, voice_off + VOICE_OFF_BRR_ADDR, next_brr_addr)
        _pack_le_u16(dsp, voice_off + VOICE_OFF_ENV, env if resume_voice else 0)
        _pack_le_i16(dsp, voice_off + VOICE_OFF_HIDDEN_ENV, env if resume_voice else 0)
        dsp[voice_off + VOICE_OFF_BUF_POS]    = 0
        dsp[voice_off + VOICE_OFF_BRR_OFFSET] = next_brr_offset
        dsp[voice_off + VOICE_OFF_KON_DELAY]  = 0
        dsp[voice_off + VOICE_OFF_ENV_MODE]   = 3 if resume_voice else 0
        if resume_voice:
            voice_envx = (env >> 4) & 0xFF
            voice_outx = _u8_from_signed_high(out_sample)
            dsp[voice_off + VOICE_OFF_T_ENVX_OUT] = voice_envx
            dsp_regs[voice * 0x10 + 0x08] = voice_envx
            dsp_regs[voice * 0x10 + 0x09] = voice_outx
            envx_buf = voice_envx
            outx_buf = voice_outx
            if uses_noise:
                noise_seed = _derive_noise_seed(out_sample, env)
        else:
            dsp[voice_off + VOICE_OFF_T_ENVX_OUT] = 0

    return resumed_keyed, envx_buf, outx_buf, noise_seed

def _build_ipl_boot_dsp_state() -> bytes:
    """Build the DSP state produced by snes9x's SPC_DSP::load(zero_regs)."""
    dsp = bytearray(SND_DSP_BYTES)
    dsp[66] = 0x01
    dsp[82] = 0x01
    dsp[DSP_REG_FLG] = 0xE0
    for voice in range(8):
        voice_off = DSP_OFF_VOICES + voice * DSP_VOICE_STRIDE
        dsp[voice_off + VOICE_OFF_BRR_OFFSET] = 1
    dsp[DSP_OFF_MISC] = 1       # every_other_sample
    _pack_le_u16(dsp, DSP_OFF_MISC + 2, 0x4000)  # noise seed
    dsp[DSP_MISC_T_ECHO_EN] = 0xE0
    dsp[DSP_OFF_EXTERNAL_REGS:DSP_OFF_EXTERNAL_REGS + 128] = _DSP_POWERON_EXTERNAL_REGS
    return bytes(dsp)

def _build_dsp_state(a01: bytes, ram: bytearray, ssz: bytes,
                     *, ipl_boot: bool = False) -> bytes:
    """Build the 642B DSP block.

    Layout (from SPC_DSP::copy_state):
      +0    m.regs[128]
      +128  voices[8] (38B each)
      +432  echo_hist[8][2] int16 (32B)
      +464  misc fields (49B)
      +513  m.external_regs[128]  (mirror of regs at save time)
      +641  final extra() byte
    """
    dsp = bytearray(SND_DSP_BYTES)
    if len(a01) < A01_OFF_EXTRA_RAM:
        return bytes(dsp)
    if ipl_boot:
        return _build_ipl_boot_dsp_state()

    dsp_regs = bytearray(a01[A01_OFF_DSP_REGS:A01_OFF_EXTRA_RAM])
    _clear_initial_echo_buffer(ram, dsp_regs)
    dsp[0:128] = dsp_regs
    dsp[DSP_OFF_EXTERNAL_REGS:DSP_OFF_EXTERNAL_REGS + 128] = dsp_regs
    _pack_le_u16(dsp, DSP_OFF_MISC + 2, 0x4000)  # valid nonzero noise LFSR seed

    keyed = a01[A01_OFF_KEYED]
    # m.every_other_sample (DSP_OFF_MISC + 0) and m.kon stay zero.
    dsp[DSP_MISC_KON] = 0

    if len(ssz) >= SR16_SSZ_SIZE:
        # SSZ is SR16's old Snes9x SoundData snapshot (1281 B). It contains
        # the voice state that A01 lacks: decoded BRR samples, current BRR
        # block address, sample pointer, and envelope. Translate the parts
        # Blargg can consume so voices continue instead of being key-on
        # restarted from the beginning of their BRR samples.
        resumed_keyed, envx_buf, outx_buf, noise_seed = _seed_voices_from_ssz(
            dsp, dsp_regs, ssz, ram, keyed
        )

        # When SSZ is present, avoid m.new_kon: key-on is what restarts
        # the BRR sample. The seeded per-voice env/buffer/brr_addr state is
        # enough for active voices to keep producing samples immediately.
        dsp[DSP_MISC_NEW_KON] = 0

        # Clear ENDX (DSP $7C) for voices we re-seeded as currently
        # playing. SR16's ENDX bit is sticky — it stays set once a voice
        # hits a BRR end-flag. After we re-seed the voice as if it's
        # mid-sample, leaving ENDX set creates an inconsistent picture
        # ("voice playing, but already ended"). Music drivers that poll
        # ENDX use it as the "voice finished its note" signal, and a
        # stale set bit can make them stop issuing keep-alive commands.
        dsp_regs[DSP_REG_ENDX] &= ~resumed_keyed & 0xFF

        echo_len = _be_u(ssz, SSZ_OFF_ECHO_LENGTH, 4)
        echo_offset = _be_u(ssz, SSZ_OFF_ECHO_OFFSET, 4)
        _pack_le_u16(dsp, DSP_MISC_ECHO_OFFSET, echo_offset)
        _pack_le_u16(dsp, DSP_MISC_ECHO_LENGTH, echo_len if echo_len else 4)
        dsp[DSP_MISC_ENDX_BUF] = dsp_regs[DSP_REG_ENDX]   # cleared value
        # Old SoundData carries the current envelope and output sample. Seed
        # the visible readback buffers too; battle engines such as FFV poll
        # ENVX/OUTX immediately around short SFX, and zeros here make active
        # effects look as if they had not started yet.
        dsp[DSP_MISC_ENVX_BUF] = envx_buf
        dsp[DSP_MISC_OUTX_BUF] = outx_buf
        dsp[DSP_MISC_T_PMON]   = dsp_regs[DSP_REG_PMON]
        dsp[DSP_MISC_T_NON]    = dsp_regs[DSP_REG_NON]
        dsp[DSP_MISC_T_EON]    = dsp_regs[DSP_REG_EON]
        dsp[DSP_MISC_T_DIR]    = dsp_regs[DSP_REG_DIR]
        dsp[DSP_MISC_T_KOFF]   = 0
        dsp[DSP_MISC_T_ESA]    = dsp_regs[DSP_REG_ESA]
        dsp[DSP_MISC_T_ECHO_EN] = dsp_regs[DSP_REG_FLG]
        if noise_seed is not None:
            _pack_le_u16(dsp, DSP_OFF_MISC + 2, noise_seed)
        dsp[0:128] = dsp_regs
        dsp[DSP_OFF_EXTERNAL_REGS:DSP_OFF_EXTERNAL_REGS + 128] = dsp_regs

    else:
        # Fallback for old saves without SSZ used to re-key active voices:
        #     dsp[DSP_MISC_NEW_KON] = keyed
        #
        # That gets audio moving, but it restarts BRR samples and can make
        # an audible click/pop at load. Current SR16 saves include SSZ, so
        # keep the fallback silent while we validate whether re-keying is
        # still needed anywhere.
        dsp[DSP_MISC_NEW_KON] = 0

    # Seed t_dir / t_esa from current DSP regs so the very first voice
    # clock has valid sample-directory and echo-area pointers
    # (matches what load() does on power-up).
    dsp[DSP_MISC_T_DIR] = dsp_regs[DSP_REG_DIR]
    dsp[DSP_MISC_T_ESA] = dsp_regs[DSP_REG_ESA]
    return bytes(dsp)


# ---------------------------------------------------------------------------
# SND assembly
# ---------------------------------------------------------------------------
