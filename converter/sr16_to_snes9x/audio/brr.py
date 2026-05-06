"""Compatibility facade for SR16 SSZ -> Blargg DSP audio helpers.

The implementation is split across smaller modules by responsibility. Keep this
module as the stable import surface for older callers that still import
internal helper names from ``converter.sr16_to_snes9x.audio.brr``.
"""
from __future__ import annotations

from .brr_decode import (
    _build_ssz_voice_window,
    _decode_brr_block,
    _next_brr_block_addr,
)
from .gauss import (
    _GAUSS_TABLE,
    _interp_gaussian,
    _predict_voice_output,
    _wrap_i16,
)
from .phase_calibration import _calibrate_ssz_voice_window
from .phase_metrics import (
    _sample_ptr_distance,
    _smooth_phase_error_limit,
    _window_max_step,
    _window_transition_energy,
)
from .phase_rules import (
    _forced_first_frame_tail_phase,
    _should_backstep_dry_moving_high_volume_phase,
    _should_backstep_ended_moving_echo_phase,
    _should_backstep_live_echo_peer_phase,
    _should_backstep_low_srcn_live_tail_phase,
    _should_backstep_quartet_boundary_phase,
    _should_backstep_smooth_echo_cluster_phase,
    _should_prefer_saved_echo_wrap_phase,
    _should_prefer_saved_sample_ptr_phase,
    _should_prefer_static_echo_saved_phase,
    _should_use_dry_ended_tail_phase,
    _should_use_late_brr_decode_offset,
)
from .voice_policy import (
    _clear_initial_echo_buffer,
    _quiet_duplicate_ssz_voice_mask,
    _s8,
    _should_resume_ssz_voice,
    _zero_circular_region,
)

__all__ = [
    '_GAUSS_TABLE',
    '_should_resume_ssz_voice',
    '_s8',
    '_quiet_duplicate_ssz_voice_mask',
    '_zero_circular_region',
    '_clear_initial_echo_buffer',
    '_decode_brr_block',
    '_next_brr_block_addr',
    '_build_ssz_voice_window',
    '_wrap_i16',
    '_interp_gaussian',
    '_predict_voice_output',
    '_sample_ptr_distance',
    '_window_transition_energy',
    '_window_max_step',
    '_should_prefer_saved_sample_ptr_phase',
    '_should_prefer_saved_echo_wrap_phase',
    '_should_backstep_ended_moving_echo_phase',
    '_should_backstep_live_echo_peer_phase',
    '_should_backstep_smooth_echo_cluster_phase',
    '_should_backstep_low_srcn_live_tail_phase',
    '_should_backstep_quartet_boundary_phase',
    '_should_backstep_dry_moving_high_volume_phase',
    '_should_prefer_static_echo_saved_phase',
    '_should_use_dry_ended_tail_phase',
    '_forced_first_frame_tail_phase',
    '_smooth_phase_error_limit',
    '_should_use_late_brr_decode_offset',
    '_calibrate_ssz_voice_window',
]
