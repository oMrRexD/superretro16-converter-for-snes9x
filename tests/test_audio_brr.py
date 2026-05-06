"""Tests for BRR/Gauss helpers in audio_brr."""
from __future__ import annotations
import pytest

from converter.sr16_to_snes9x.audio.brr import (
    _GAUSS_TABLE,
    _wrap_i16,
    _interp_gaussian,
    _next_brr_block_addr,
    _decode_brr_block,
    _sample_ptr_distance,
    _s8,
    _zero_circular_region,
    _clear_initial_echo_buffer,
    _should_resume_ssz_voice,
    _quiet_duplicate_ssz_voice_mask,
    _should_prefer_saved_sample_ptr_phase,
    _should_prefer_saved_echo_wrap_phase,
    _should_backstep_ended_moving_echo_phase,
    _should_backstep_live_echo_peer_phase,
    _should_backstep_smooth_echo_cluster_phase,
    _should_backstep_low_srcn_live_tail_phase,
    _should_backstep_quartet_boundary_phase,
    _should_backstep_dry_moving_high_volume_phase,
    _forced_first_frame_tail_phase,
    _should_use_late_brr_decode_offset,
)


def test_gauss_table_has_512_entries():
    """Blargg interpolator indexes gauss[fwd|fwd+256|rev+256|rev], so we need
    a table that covers indices 0..511 inclusive — 512 entries total."""
    assert len(_GAUSS_TABLE) == 512


def test_wrap_i16_signed_extension():
    assert _wrap_i16(0) == 0
    assert _wrap_i16(0x7FFF) == 32767
    assert _wrap_i16(0x8000) == -32768
    assert _wrap_i16(0xFFFF) == -1
    assert _wrap_i16(0x10001) == 1   # wraps high bits


def test_s8_signed_extension():
    assert _s8(0) == 0
    assert _s8(0x7F) == 127
    assert _s8(0x80) == -128
    assert _s8(0xFF) == -1


def test_sample_ptr_distance_cyclic():
    # Distance is the smaller of forward/backward steps modulo 16.
    assert _sample_ptr_distance(0, 0) == 0
    assert _sample_ptr_distance(0, 8) == 8
    assert _sample_ptr_distance(0, 9) == 7   # going backwards is shorter
    assert _sample_ptr_distance(15, 0) == 1
    assert _sample_ptr_distance(3, 13) == 6


@pytest.mark.parametrize("header_flags,expect_loop,loop_addr,expected_next", [
    # Plain block: header bit 0 clear -> next = +9
    (0x00, False, None, 9),
    # End-of-sample but not loop: returns None
    (0x01, False, 0x1234, None),
    # End-of-sample WITH loop: returns loop_addr
    (0x03, True, 0x4242, 0x4242),
])
def test_next_brr_block_addr(header_flags, expect_loop, loop_addr, expected_next):
    spc_ram = bytearray(0x10000)
    spc_ram[0] = header_flags
    next_addr = _next_brr_block_addr(spc_ram, 0, loop_addr)
    assert next_addr == expected_next


def test_decode_brr_block_zero_yields_silence():
    # Header = 0 means shift=0, filter=0, no end/loop. All 8 data bytes 0.
    spc_ram = bytearray(0x10000)
    header, samples, p2, p1 = _decode_brr_block(spc_ram, 0, 0, 0)
    assert header == 0
    assert samples == [0] * 16
    assert (p2, p1) == (0, 0)


def test_decode_brr_block_uses_shift_for_amplitude():
    # Header shift=4, filter=0 (direct). Single nibble = 1 -> sample = (1<<4)>>1 = 8
    # then doubled by Blargg -> 16.
    spc_ram = bytearray(0x10000)
    spc_ram[0] = 0x40           # shift=4 filter=0
    spc_ram[1] = 0x10           # nibbles: hi=1, lo=0
    _h, samples, _p2, _p1 = _decode_brr_block(spc_ram, 0, 0, 0)
    assert samples[0] == 16
    assert samples[1] == 0


def test_interp_gaussian_with_constant_buffer_yields_constant():
    """A constant buffer should reproduce the input through the interpolator
    (gauss taps sum to ~2^11 by design so a constant signal stays put)."""
    buf = [1000] * 12
    out = _interp_gaussian(buf, 0)
    # The four-tap gaussian at interp_pos=0 is gauss[255]=1305, gauss[256]=1305
    # plus tiny side taps; result is roughly samples[1] (= 1000), within rounding.
    assert 990 <= out <= 1010
    # Output is forced to even (& ~1)
    assert out & 1 == 0


def test_interp_gaussian_silence_is_zero():
    assert _interp_gaussian([0] * 12, 0) == 0


def test_zero_circular_region_wraps_at_64k():
    buf = bytearray(b"\xff" * 0x10000)
    _zero_circular_region(buf, 0xFFF8, 16)
    # 8 bytes zeroed at the end, 8 wrapped to start
    assert buf[0xFFF8:0x10000] == b"\x00" * 8
    assert buf[0:8] == b"\x00" * 8
    assert buf[8] == 0xFF


def test_zero_circular_region_zero_count_is_noop():
    buf = bytearray(b"\xab" * 16)
    _zero_circular_region(buf, 0, 0)
    assert buf == b"\xab" * 16


def test_clear_initial_echo_buffer_uses_dsp_esa_and_edl():
    ram = bytearray(b"\xff" * 0x10000)
    dsp_regs = bytearray(128)
    dsp_regs[0x6D] = 0x40   # ESA = $4000 (page << 8)
    dsp_regs[0x7D] = 0x02   # EDL low 4 bits = 2 -> 2 * 0x800 = 0x1000 bytes
    _clear_initial_echo_buffer(ram, dsp_regs)
    # Clears bytes [$4000, $4000+0x1000)
    assert ram[0x4000:0x5000] == b"\x00" * 0x1000
    # Outside region untouched
    assert ram[0x3FFF] == 0xFF
    assert ram[0x5000] == 0xFF


def test_clear_initial_echo_buffer_zero_length_noop():
    ram = bytearray(b"\xff" * 0x10000)
    dsp_regs = bytearray(128)
    dsp_regs[0x7D] = 0   # EDL=0 -> echo length 0
    _clear_initial_echo_buffer(ram, dsp_regs)
    assert all(b == 0xFF for b in ram[:16])


def test_should_resume_ssz_voice():
    # Noise voices still need their envelope/readback state restored; only the
    # LFSR phase is approximated by the SND builder.
    assert _should_resume_ssz_voice(active=True, uses_noise=False)
    assert not _should_resume_ssz_voice(active=False, uses_noise=False)
    assert _should_resume_ssz_voice(active=True, uses_noise=True)
    assert not _should_resume_ssz_voice(active=False, uses_noise=True)


def test_quiet_duplicate_ssz_voice_mask_includes_echo_tails():
    ssz = bytearray(1281)
    dsp_regs = bytearray(128)
    keyed = 0x03

    for voice in (0, 1):
        base = 0x30 + voice * 0x75
        ext = 0x3DC + voice * 0x22
        ssz[base:base + 4] = (1).to_bytes(4, "big")
        ssz[ext + 0x02:ext + 0x06] = (0x600).to_bytes(4, "big")
        dsp_regs[voice * 0x10 + 0x04] = 0x20

    dsp_regs[0x00] = 6
    dsp_regs[0x01] = 6
    dsp_regs[0x10] = 1
    dsp_regs[0x11] = 1
    dsp_regs[0x4D] = 0x02

    assert _quiet_duplicate_ssz_voice_mask(bytes(ssz), bytes(dsp_regs), keyed) == 0x02


def test_quiet_duplicate_ssz_voice_mask_requires_louder_peer():
    ssz = bytearray(1281)
    dsp_regs = bytearray(128)
    voice = 1
    base = 0x30 + voice * 0x75
    ext = 0x3DC + voice * 0x22
    ssz[base:base + 4] = (1).to_bytes(4, "big")
    ssz[ext + 0x02:ext + 0x06] = (0x600).to_bytes(4, "big")
    dsp_regs[voice * 0x10 + 0x00] = 1
    dsp_regs[voice * 0x10 + 0x01] = 1
    dsp_regs[voice * 0x10 + 0x04] = 0x20
    dsp_regs[0x4D] = 0x02

    assert _quiet_duplicate_ssz_voice_mask(bytes(ssz), bytes(dsp_regs), 0x02) == 0


def test_quiet_duplicate_ssz_voice_mask_keeps_echo_pair_without_dry_anchor():
    ssz = bytearray(1281)
    dsp_regs = bytearray(128)
    keyed = 0x03

    for voice in (0, 1):
        base = 0x30 + voice * 0x75
        ext = 0x3DC + voice * 0x22
        ssz[base:base + 4] = (1).to_bytes(4, "big")
        ssz[ext + 0x02:ext + 0x06] = (0x600).to_bytes(4, "big")
        dsp_regs[voice * 0x10 + 0x04] = 0x20

    dsp_regs[0x00] = 12
    dsp_regs[0x01] = 12
    dsp_regs[0x10] = 1
    dsp_regs[0x11] = 1
    dsp_regs[0x4D] = 0x03

    assert _quiet_duplicate_ssz_voice_mask(bytes(ssz), bytes(dsp_regs), keyed) == 0


def test_prefer_saved_sample_ptr_phase_when_output_match_is_rough():
    assert _should_prefer_saved_sample_ptr_phase(
        sample_distance=4,
        best_error=100,
        saved_error=3000,
        best_buf12=[0, 6000, -6000, 6000, -6000, 6000, -6000, 6000],
        saved_buf12=[0, 500, 1000, 1500, 2000, 2500, 3000, 3500],
    )


def test_prefer_saved_sample_ptr_phase_for_near_phase_with_sharp_discontinuity():
    assert _should_prefer_saved_sample_ptr_phase(
        sample_distance=1,
        best_error=116,
        saved_error=564,
        best_buf12=[-5918, -3702, -22828, -23002, -22704, -22228],
        saved_buf12=[-22704, -22228, -21730, -21098, -20234, -19050],
    )


def test_prefer_saved_sample_ptr_phase_keeps_close_clean_match():
    assert not _should_prefer_saved_sample_ptr_phase(
        sample_distance=1,
        best_error=10,
        saved_error=50,
        best_buf12=[0, 2794, 3000, 4596, 4596, 4596],
        saved_buf12=[0, 94, 188, 282, 324, 324],
    )


def test_prefer_saved_sample_ptr_phase_for_moderate_rough_shift():
    assert _should_prefer_saved_sample_ptr_phase(
        sample_distance=4,
        best_error=240,
        saved_error=1408,
        best_buf12=[0, 5000, 0, 5000, 0, 5000, 0, 5000],
        saved_buf12=[0, 1000, 2000, 3000, 4000, 5000, 6000, 7000],
    )


def test_prefer_saved_sample_ptr_phase_has_conservative_guards():
    smooth = [0, 500, 1000, 1500, 2000, 2500, 3000, 3500]
    rough = [0, 6000, -6000, 6000, -6000, 6000, -6000, 6000]

    assert not _should_prefer_saved_sample_ptr_phase(
        sample_distance=3,
        best_error=100,
        saved_error=3000,
        best_buf12=rough,
        saved_buf12=smooth,
    )
    assert not _should_prefer_saved_sample_ptr_phase(
        sample_distance=4,
        best_error=100,
        saved_error=1601,
        best_buf12=rough,
        saved_buf12=smooth,
    )
    assert not _should_prefer_saved_sample_ptr_phase(
        sample_distance=4,
        best_error=100,
        saved_error=3000,
        best_buf12=smooth,
        saved_buf12=rough,
    )


def test_prefer_saved_echo_wrap_phase_for_moving_echo_voice():
    assert _should_prefer_saved_echo_wrap_phase(
        best_phase=0x0A,
        saved_phase=0x0C,
        best_error=250,
        saved_error=810,
        best_buf12=[-11030, -11778, -12368, -13050, -13668, -14334],
        saved_buf12=[-13668, -14334, -15026, -15718, -16262, -16778],
        echo_enabled=True,
        envelope_moving=True,
        voice_ended=False,
    )


def test_prefer_saved_echo_wrap_phase_keeps_non_echo_matches():
    assert not _should_prefer_saved_echo_wrap_phase(
        best_phase=0x0A,
        saved_phase=0x0C,
        best_error=250,
        saved_error=810,
        best_buf12=[-11030, -11778, -12368, -13050, -13668, -14334],
        saved_buf12=[-13668, -14334, -15026, -15718, -16262, -16778],
        echo_enabled=False,
        envelope_moving=True,
        voice_ended=False,
    )


def test_backstep_ended_moving_echo_phase_when_neighbor_is_plausible():
    assert _should_backstep_ended_moving_echo_phase(
        best_phase=0x0E,
        best_error=432,
        back_error=3298,
        best_buf12=[1816, 7104, 10814, 14978, 19434, 21980],
        back_buf12=[1816, 7104, 10814, 14978, 19434, 21980],
        echo_enabled=True,
        envelope_moving=True,
        voice_ended=True,
    )


def test_backstep_live_echo_peer_phase_when_previous_phase_is_better():
    assert _should_backstep_live_echo_peer_phase(
        saved_error=2010,
        prev_error=252,
        saved_buf12=[-17232, -19998, -22224, -24130, -25420, -25838],
        prev_buf12=[-17232, -19998, -22224, -24130, -25420, -25838],
        echo_enabled=True,
        envelope_moving=True,
        voice_ended=False,
        same_srcn_ended_peer=True,
    )


def test_backstep_smooth_echo_cluster_phase_when_quartet_jump_is_too_far():
    assert _should_backstep_smooth_echo_cluster_phase(
        saved_phase=1,
        chosen_phase=8,
        chosen_error=948,
        back_error=1890,
        chosen_buf12=[-13730, -11178, -8440, -6124, -4786, -4408],
        back_buf12=[-10140, -12074, -14024, -14904, -13730, -11178],
        echo_enabled=True,
        envelope_moving=False,
        voice_ended=False,
        same_srcn_active_count=3,
    )


def test_backstep_low_srcn_live_tail_phase_is_narrow():
    assert _should_backstep_low_srcn_live_tail_phase(
        saved_phase=1,
        best_phase=5,
        best_error=80,
        low_srcn_voice=True,
        echo_enabled=False,
        envelope_moving=False,
        voice_ended=False,
    )
    assert not _should_backstep_low_srcn_live_tail_phase(
        saved_phase=1,
        best_phase=5,
        best_error=80,
        low_srcn_voice=True,
        echo_enabled=True,
        envelope_moving=False,
        voice_ended=False,
    )


def test_backstep_quartet_boundary_phase_skips_moving_envelope():
    assert _should_backstep_quartet_boundary_phase(
        best_phase=8,
        best_error=44,
        best_transition=17530,
        back_error=206,
        back_transition=7672,
        voice_ended=True,
        envelope_moving=False,
    )
    assert not _should_backstep_quartet_boundary_phase(
        best_phase=8,
        best_error=44,
        best_transition=17530,
        back_error=206,
        back_transition=7672,
        voice_ended=True,
        envelope_moving=True,
    )


def test_backstep_quartet_boundary_phase_keeps_clean_exact_echo_match():
    assert not _should_backstep_quartet_boundary_phase(
        best_phase=0,
        best_error=50,
        best_transition=16858,
        back_error=3798,
        back_transition=30360,
        voice_ended=True,
        envelope_moving=False,
    )


def test_backstep_dry_moving_high_volume_phase_handles_dkc_s00_shape():
    assert _should_backstep_dry_moving_high_volume_phase(
        saved_phase=0x0A,
        best_phase=0x09,
        best_error=350,
        back_error=944,
        best_buf12=[
            -18830, -19152, -20138, -20948,
            -22336, -23196, -24302, -24580,
        ],
        back_buf12=[
            -18012, -17834, -17880, -18134,
            -18830, -19152, -20138, -20948,
        ],
        echo_enabled=False,
        envelope_moving=True,
        voice_ended=False,
        voice_volume_sum=160,
    )


def test_backstep_dry_moving_high_volume_phase_rejects_quiet_or_non_mid_phase():
    common = {
        "best_error": 350,
        "back_error": 944,
        "best_buf12": [-18830, -19152, -20138, -20948, -22336, -23196],
        "back_buf12": [-18012, -17834, -17880, -18134, -18830, -19152],
        "echo_enabled": False,
        "envelope_moving": True,
        "voice_ended": False,
    }
    assert not _should_backstep_dry_moving_high_volume_phase(
        saved_phase=0x0A,
        best_phase=0x09,
        voice_volume_sum=80,
        **common,
    )
    assert not _should_backstep_dry_moving_high_volume_phase(
        saved_phase=0x04,
        best_phase=0x02,
        voice_volume_sum=160,
        **common,
    )


def test_forced_first_frame_tail_phase_handles_confirmed_tail_shapes():
    assert _forced_first_frame_tail_phase(
        saved_phase=0x06,
        pitch=0x0F10,
        env=0x7FF,
        echo_enabled=True,
        envelope_moving=False,
        voice_ended=True,
        voice_volume_sum=20,
        low_srcn_voice=False,
        srcn=0x1A,
    ) == (0x03, 3)
    assert _forced_first_frame_tail_phase(
        saved_phase=0x00,
        pitch=0x13D0,
        env=0x7FF,
        echo_enabled=True,
        envelope_moving=False,
        voice_ended=True,
        voice_volume_sum=39,
        low_srcn_voice=False,
        srcn=0x2B,
    ) == (0x04, 1)
    assert _forced_first_frame_tail_phase(
        saved_phase=0x0F,
        pitch=0x0F00,
        env=0x7FF,
        echo_enabled=True,
        envelope_moving=False,
        voice_ended=True,
        voice_volume_sum=20,
        low_srcn_voice=False,
        srcn=0x1A,
    ) == (0x03, 3)
    assert _forced_first_frame_tail_phase(
        saved_phase=0x0A,
        pitch=0x2568,
        env=0x7FF,
        echo_enabled=True,
        envelope_moving=False,
        voice_ended=True,
        voice_volume_sum=13,
        low_srcn_voice=True,
        srcn=0x03,
    ) == (0x04, 3)
    assert _forced_first_frame_tail_phase(
        saved_phase=0x0D,
        pitch=0x0ED0,
        env=0x7FF,
        echo_enabled=False,
        envelope_moving=False,
        voice_ended=True,
        voice_volume_sum=36,
        low_srcn_voice=False,
        srcn=0x2B,
    ) == (0x04, 3)
    assert _forced_first_frame_tail_phase(
        saved_phase=0x07,
        pitch=0x2A70,
        env=0x7FF,
        echo_enabled=True,
        envelope_moving=False,
        voice_ended=False,
        voice_volume_sum=52,
        low_srcn_voice=False,
        srcn=0x2D,
    ) == (0x0C, 5)
    assert _forced_first_frame_tail_phase(
        saved_phase=0x09,
        pitch=0x20DE,
        env=0x65E,
        echo_enabled=False,
        envelope_moving=True,
        voice_ended=True,
        voice_volume_sum=77,
        low_srcn_voice=True,
        srcn=0x06,
    ) == (0x00, 3)
    assert _forced_first_frame_tail_phase(
        saved_phase=0x08,
        pitch=0x1A1C,
        env=0x4F6,
        echo_enabled=True,
        envelope_moving=True,
        voice_ended=True,
        voice_volume_sum=26,
        low_srcn_voice=False,
        srcn=0x29,
    ) == (0x0E, 3)
    assert _forced_first_frame_tail_phase(
        saved_phase=0x07,
        pitch=0x138F,
        env=0x66C,
        echo_enabled=True,
        envelope_moving=True,
        voice_ended=True,
        voice_volume_sum=25,
        low_srcn_voice=False,
        srcn=0x29,
    ) == (0x0B, 7)
    assert _forced_first_frame_tail_phase(
        saved_phase=0x0F,
        pitch=0x0F00,
        env=0x7FF,
        echo_enabled=True,
        envelope_moving=True,
        voice_ended=True,
        voice_volume_sum=20,
        low_srcn_voice=False,
        srcn=0x1A,
    ) == (0x03, 3)
    assert _forced_first_frame_tail_phase(
        saved_phase=0x05,
        pitch=0x02E6,
        env=0x61F,
        echo_enabled=True,
        envelope_moving=True,
        voice_ended=True,
        voice_volume_sum=50,
        low_srcn_voice=False,
        srcn=0x20,
    ) == (0x00, 3)
    assert _forced_first_frame_tail_phase(
        saved_phase=0x0D,
        pitch=0x0ED0,
        env=0x7FF,
        echo_enabled=False,
        envelope_moving=True,
        voice_ended=True,
        voice_volume_sum=36,
        low_srcn_voice=False,
        srcn=0x2B,
    ) == (0x04, 3)
    assert _forced_first_frame_tail_phase(
        saved_phase=0x0B,
        pitch=0x0430,
        env=0x74F,
        echo_enabled=False,
        envelope_moving=True,
        voice_ended=True,
        voice_volume_sum=68,
        low_srcn_voice=False,
        srcn=0x19,
    ) == (0x01, 3)


def test_forced_first_frame_tail_phase_rejects_nearby_good_shapes():
    common = {
        "env": 0x7FF,
        "echo_enabled": True,
        "voice_ended": True,
        "low_srcn_voice": False,
    }
    assert _forced_first_frame_tail_phase(
        saved_phase=0x00,
        pitch=0x12D2,
        envelope_moving=False,
        voice_volume_sum=42,
        srcn=0x26,
        **common,
    ) is None
    assert _forced_first_frame_tail_phase(
        saved_phase=0x0A,
        pitch=0x2150,
        envelope_moving=True,
        voice_volume_sum=29,
        srcn=0x24,
        **common,
    ) is None
    assert _forced_first_frame_tail_phase(
        saved_phase=0x0B,
        pitch=0x1A67,
        env=0x69D,
        echo_enabled=True,
        envelope_moving=True,
        voice_ended=True,
        voice_volume_sum=65,
        low_srcn_voice=False,
        srcn=0x20,
    ) is None


def test_late_brr_decode_offset_handles_confirmed_non_muting_shapes():
    assert _should_use_late_brr_decode_offset(
        saved_phase=7,
        chosen_phase=5,
        current_offset=3,
        voice_volume_sum=42,
        srcn=0x22,
        same_srcn_active_count=1,
        echo_enabled=True,
        envelope_moving=False,
        voice_ended=False,
    )
    assert _should_use_late_brr_decode_offset(
        saved_phase=5,
        chosen_phase=8,
        current_offset=1,
        voice_volume_sum=23,
        srcn=0x2B,
        same_srcn_active_count=3,
        echo_enabled=False,
        envelope_moving=False,
        voice_ended=True,
    )
    assert _should_use_late_brr_decode_offset(
        saved_phase=0x0D,
        chosen_phase=0x0D,
        current_offset=3,
        voice_volume_sum=33,
        srcn=0x1B,
        same_srcn_active_count=2,
        echo_enabled=False,
        envelope_moving=False,
        voice_ended=False,
    )


def test_late_brr_decode_offset_rejects_known_false_audio_targets():
    assert not _should_use_late_brr_decode_offset(
        saved_phase=0x0F,
        chosen_phase=0x0F,
        current_offset=3,
        voice_volume_sum=10,
        srcn=0x19,
        same_srcn_active_count=4,
        echo_enabled=True,
        envelope_moving=False,
        voice_ended=False,
    )
    assert not _should_use_late_brr_decode_offset(
        saved_phase=0,
        chosen_phase=9,
        current_offset=1,
        voice_volume_sum=16,
        srcn=0x0F,
        same_srcn_active_count=7,
        echo_enabled=True,
        envelope_moving=True,
        voice_ended=True,
    )
    assert not _should_use_late_brr_decode_offset(
        saved_phase=0x0B,
        chosen_phase=9,
        current_offset=1,
        voice_volume_sum=18,
        srcn=0x1F,
        same_srcn_active_count=3,
        echo_enabled=False,
        envelope_moving=False,
        voice_ended=True,
    )


def test_quiet_duplicate_ssz_voice_mask_mutes_tiny_unanchored_echo_tails():
    ssz = bytearray(1281)
    dsp_regs = bytearray(128)
    keyed = 0x03

    for voice in (0, 1):
        base = 0x30 + voice * 0x75
        ext = 0x3DC + voice * 0x22
        ssz[base:base + 4] = (1).to_bytes(4, "big")
        ssz[ext + 0x02:ext + 0x06] = (0x600).to_bytes(4, "big")
        dsp_regs[voice * 0x10 + 0x04] = 0x20
        dsp_regs[voice * 0x10 + 0x00] = 5

    dsp_regs[0x4D] = 0x03

    assert _quiet_duplicate_ssz_voice_mask(bytes(ssz), bytes(dsp_regs), keyed) == 0x03


def test_quiet_duplicate_ssz_voice_mask_keeps_tiny_echo_with_louder_echo_peer():
    ssz = bytearray(1281)
    dsp_regs = bytearray(128)
    keyed = 0x03

    for voice in (0, 1):
        base = 0x30 + voice * 0x75
        ext = 0x3DC + voice * 0x22
        ssz[base:base + 4] = (1).to_bytes(4, "big")
        ssz[ext + 0x02:ext + 0x06] = (0x600).to_bytes(4, "big")
        dsp_regs[voice * 0x10 + 0x04] = 0x20

    dsp_regs[0x00] = 13
    dsp_regs[0x01] = 13
    dsp_regs[0x10] = 1
    dsp_regs[0x11] = 1
    dsp_regs[0x4D] = 0x03

    assert _quiet_duplicate_ssz_voice_mask(bytes(ssz), bytes(dsp_regs), keyed) == 0


def test_quiet_duplicate_ssz_voice_mask_mutes_ended_echo_peer_tail():
    ssz = bytearray(1281)
    dsp_regs = bytearray(128)
    keyed = 0

    for voice, vol in ((0, 30), (2, 16), (3, 10)):
        base = 0x30 + voice * 0x75
        ext = 0x3DC + voice * 0x22
        ssz[base:base + 4] = (3).to_bytes(4, "big")
        ssz[ext + 0x02:ext + 0x06] = (0x7FF).to_bytes(4, "big")
        dsp_regs[voice * 0x10 + 0x04] = 0x21
        dsp_regs[voice * 0x10 + 0x00] = vol
        dsp_regs[voice * 0x10 + 0x01] = vol
        keyed |= 1 << voice

    # Voice 3 is a quiet, already-ended echo companion. Voice 2 is also ended
    # but still too loud to be treated as a stale tail.
    dsp_regs[0x4D] = keyed
    dsp_regs[0x7C] = (1 << 2) | (1 << 3)

    assert _quiet_duplicate_ssz_voice_mask(bytes(ssz), bytes(dsp_regs), keyed) == 0x08


def test_quiet_duplicate_ssz_voice_mask_mutes_ended_echo_with_dry_peer():
    ssz = bytearray(1281)
    dsp_regs = bytearray(128)
    keyed = 0

    for voice, vol, echo, ended in (
        (0, 12, False, True),
        (1, 9, False, False),
        (7, 19, True, True),
    ):
        base = 0x30 + voice * 0x75
        ext = 0x3DC + voice * 0x22
        ssz[base:base + 4] = (3).to_bytes(4, "big")
        ssz[ext + 0x02:ext + 0x06] = (0x7FF).to_bytes(4, "big")
        dsp_regs[voice * 0x10 + 0x04] = 0x2B
        dsp_regs[voice * 0x10 + 0x00] = vol
        dsp_regs[voice * 0x10 + 0x01] = vol
        if echo:
            dsp_regs[0x4D] |= 1 << voice
        if ended:
            dsp_regs[0x7C] |= 1 << voice
        keyed |= 1 << voice

    assert _quiet_duplicate_ssz_voice_mask(bytes(ssz), bytes(dsp_regs), keyed) == 0x80


def test_quiet_duplicate_ssz_voice_mask_mutes_tiny_ended_dry_peer():
    ssz = bytearray(1281)
    dsp_regs = bytearray(128)
    keyed = 0

    for voice, vol, echo, ended in (
        (2, 10, True, False),
        (3, 5, True, False),
        (4, 10, False, True),
        (5, 1, False, True),
    ):
        base = 0x30 + voice * 0x75
        ext = 0x3DC + voice * 0x22
        ssz[base:base + 4] = (3).to_bytes(4, "big")
        ssz[ext + 0x02:ext + 0x06] = (0x7FF).to_bytes(4, "big")
        dsp_regs[voice * 0x10 + 0x04] = 0x19
        dsp_regs[voice * 0x10 + 0x00] = vol
        dsp_regs[voice * 0x10 + 0x01] = vol
        if echo:
            dsp_regs[0x4D] |= 1 << voice
        if ended:
            dsp_regs[0x7C] |= 1 << voice
        keyed |= 1 << voice

    assert _quiet_duplicate_ssz_voice_mask(bytes(ssz), bytes(dsp_regs), keyed) == 0x20


def test_quiet_duplicate_ssz_voice_mask_mutes_live_echo_cluster_lead():
    ssz = bytearray(1281)
    dsp_regs = bytearray(128)
    keyed = 0

    for voice, env, vol, ended in (
        (0, 1943, 7, True),
        (1, 726, 7, True),
        (2, 1008, 8, True),
        (3, 1388, 8, True),
        (4, 1943, 19, False),
        (5, 1388, 17, True),
        (6, 726, 14, True),
    ):
        base = 0x30 + voice * 0x75
        ext = 0x3DC + voice * 0x22
        ssz[base:base + 4] = (3).to_bytes(4, "big")
        ssz[base + 0x23:base + 0x27] = (1).to_bytes(4, "big")
        ssz[ext + 0x02:ext + 0x06] = env.to_bytes(4, "big")
        dsp_regs[voice * 0x10 + 0x04] = 0x0F
        dsp_regs[voice * 0x10 + 0x00] = vol
        dsp_regs[voice * 0x10 + 0x01] = vol
        dsp_regs[0x4D] |= 1 << voice
        if ended:
            dsp_regs[0x7C] |= 1 << voice
        keyed |= 1 << voice

    assert _quiet_duplicate_ssz_voice_mask(bytes(ssz), bytes(dsp_regs), keyed) == 0x10


def test_quiet_duplicate_ssz_voice_mask_keeps_smaller_live_echo_cluster_voice():
    ssz = bytearray(1281)
    dsp_regs = bytearray(128)
    keyed = 0

    for voice, vol, ended in (
        (0, 7, True),
        (1, 7, True),
        (2, 8, True),
        (3, 8, True),
        (4, 15, False),
        (5, 17, True),
        (6, 14, True),
    ):
        base = 0x30 + voice * 0x75
        ext = 0x3DC + voice * 0x22
        ssz[base:base + 4] = (3).to_bytes(4, "big")
        ssz[base + 0x23:base + 0x27] = (1).to_bytes(4, "big")
        ssz[ext + 0x02:ext + 0x06] = (0x700).to_bytes(4, "big")
        dsp_regs[voice * 0x10 + 0x04] = 0x0F
        dsp_regs[voice * 0x10 + 0x00] = vol
        dsp_regs[voice * 0x10 + 0x01] = vol
        dsp_regs[0x4D] |= 1 << voice
        if ended:
            dsp_regs[0x7C] |= 1 << voice
        keyed |= 1 << voice

    assert _quiet_duplicate_ssz_voice_mask(bytes(ssz), bytes(dsp_regs), keyed) == 0
