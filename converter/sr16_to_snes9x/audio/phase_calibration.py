"""Top-level SSZ voice phase calibration orchestration.

Tracing: when ``CONVERTER_TRACE`` is set in the environment, every time a
narrow phase rule fires (i.e. changes the voice's chosen state away from
the smooth-fallback default), a ``TRACE phase_rule rule_id=R<n> ...`` line
is emitted. The rule_id list lives in the docstring of ``phase_rules.py``.
This is the diagnostic of choice when triaging an unknown audio glitch:
spot which rule fires for the misbehaving voice, then audit that rule's
guard with respect to the new save's DSP shape.
"""
from __future__ import annotations

from .brr_decode import _build_ssz_voice_window
from .gauss import _predict_voice_output
from converter.common._trace import trace as _trace
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

def _calibrate_ssz_voice_window(spc_ram: bytes,
                                current_block_addr: int,
                                loop_block_addr: int | None,
                                decoded_block: list[int],
                                prev_last2: tuple[int, int],
                                sample_ptr: int,
                                saved_out_sample: int,
                                env: int,
                                *,
                                voice_ended: bool = False,
                                echo_enabled: bool = False,
                                envelope_moving: bool = False,
                                same_srcn_ended_peer: bool = False,
                                same_srcn_active_count: int = 0,
                                low_srcn_voice: bool = False,
                                srcn: int = 0,
                                pitch: int = 0,
                                voice_volume_sum: int = 0,
                                ) -> tuple[int, list[int], int, int, int]:
    """Choose the sample pointer whose predicted output best matches SSZ.

    Returns `(best_sample_ptr, buf12, interp_pos, next_brr_addr, next_brr_offset)`.

    Searches the full 0..15 window and ranks candidates primarily by how well
    the seeded buffer would reproduce the saved `out_sample`, with the
    distance from the recorded `sample_pointer` as a tie-breaker.
    """
    saved_phase = sample_ptr & 0x0F
    best_key: tuple[int, int] | None = None
    best_state: tuple[int, list[int], int, int, int] | None = None
    saved_key: tuple[int, int] | None = None
    saved_state: tuple[int, list[int], int, int, int] | None = None
    candidates: dict[int, tuple[tuple[int, int], tuple[int, list[int], int, int, int]]] = {}

    for cand in range(16):
        buf12, interp_pos, next_brr_addr, next_brr_offset = _build_ssz_voice_window(
            spc_ram, current_block_addr, loop_block_addr, decoded_block, prev_last2, cand
        )
        predicted = _predict_voice_output(buf12, interp_pos, env)
        key = (
            abs(predicted - saved_out_sample),
            _sample_ptr_distance(cand, sample_ptr),
        )
        state = (cand, buf12, interp_pos, next_brr_addr, next_brr_offset)
        candidates[cand] = (key, state)
        if cand == saved_phase:
            saved_key = key
            saved_state = state
        if best_key is None or key < best_key:
            best_key = key
            best_state = state

    def with_late_offset(
        state: tuple[int, list[int], int, int, int]
    ) -> tuple[int, list[int], int, int, int]:
        if _should_use_late_brr_decode_offset(
            saved_phase=saved_phase,
            chosen_phase=state[0],
            current_offset=state[4],
            voice_volume_sum=voice_volume_sum,
            srcn=srcn,
            same_srcn_active_count=same_srcn_active_count,
            echo_enabled=echo_enabled,
            envelope_moving=envelope_moving,
            voice_ended=voice_ended,
        ):
            _trace("phase_rule", rule_id="R12",
                   srcn=srcn, pitch=pitch,
                   chosen_phase=state[0], saved_phase=saved_phase)
            return (state[0], state[1], state[2], state[3], 5)
        return state

    def with_forced_offset(
        state: tuple[int, list[int], int, int, int],
        offset: int,
    ) -> tuple[int, list[int], int, int, int]:
        return (state[0], state[1], state[2], state[3], offset & 0xFF)

    assert best_state is not None
    assert best_key is not None
    forced_tail = _forced_first_frame_tail_phase(
        saved_phase=saved_phase,
        pitch=pitch,
        env=env,
        echo_enabled=echo_enabled,
        envelope_moving=envelope_moving,
        voice_ended=voice_ended,
        voice_volume_sum=voice_volume_sum,
        low_srcn_voice=low_srcn_voice,
        srcn=srcn,
    )
    if forced_tail is not None:
        forced_phase, forced_offset = forced_tail
        _forced_key, forced_state = candidates[forced_phase]
        _trace("phase_rule", rule_id="R11",
               srcn=srcn, pitch=pitch,
               saved_phase=saved_phase,
               forced_phase=forced_phase, forced_offset=forced_offset)
        return with_forced_offset(forced_state, forced_offset)

    if saved_state is not None and saved_key is not None:
        sample_distance = _sample_ptr_distance(best_state[0], saved_phase)
        if _should_prefer_saved_echo_wrap_phase(
            best_phase=best_state[0],
            saved_phase=saved_phase,
            best_error=best_key[0],
            saved_error=saved_key[0],
            best_buf12=best_state[1],
            saved_buf12=saved_state[1],
            echo_enabled=echo_enabled,
            envelope_moving=envelope_moving,
            voice_ended=voice_ended,
        ):
            _trace("phase_rule", rule_id="R2",
                   srcn=srcn, pitch=pitch,
                   best_phase=best_state[0], saved_phase=saved_phase)
            return with_late_offset(saved_state)
        if _should_prefer_saved_sample_ptr_phase(
            sample_distance=sample_distance,
            best_error=best_key[0],
            saved_error=saved_key[0],
            best_buf12=best_state[1],
            saved_buf12=saved_state[1],
        ):
            _trace("phase_rule", rule_id="R1",
                   srcn=srcn, pitch=pitch,
                   best_phase=best_state[0], saved_phase=saved_phase,
                   sample_distance=sample_distance)
            return with_late_offset(saved_state)
        if _should_prefer_static_echo_saved_phase(
            saved_phase=saved_phase,
            best_phase=best_state[0],
            best_error=best_key[0],
            saved_error=saved_key[0],
            best_buf12=best_state[1],
            saved_buf12=saved_state[1],
            echo_enabled=echo_enabled,
            envelope_moving=envelope_moving,
            voice_ended=voice_ended,
            voice_volume_sum=voice_volume_sum,
        ):
            _trace("phase_rule", rule_id="R9",
                   srcn=srcn, pitch=pitch,
                   best_phase=best_state[0], saved_phase=saved_phase)
            return with_late_offset(saved_state)

    # If old SoundData says ENDX had already latched for this voice, a best
    # match on the first phase of a quartet often means we advanced one DSP
    # decode step too far. Back up by one phase when that alternative is still
    # plausibly close; this removes first-frame pops without muting legitimate
    # sustained ambience.
    best_phase = best_state[0]
    best_transition = _window_transition_energy(best_state[1])
    best_max_step = _window_max_step(best_state[1])
    if _should_backstep_low_srcn_live_tail_phase(
        saved_phase=saved_phase,
        best_phase=best_phase,
        best_error=best_key[0],
        low_srcn_voice=low_srcn_voice,
        echo_enabled=echo_enabled,
        envelope_moving=envelope_moving,
        voice_ended=voice_ended,
    ):
        low_tail_phase = (saved_phase - 1) & 0x0F
        _low_tail_key, low_tail_state = candidates[low_tail_phase]
        _trace("phase_rule", rule_id="R6",
               srcn=srcn, pitch=pitch,
               best_phase=best_phase, saved_phase=saved_phase)
        return with_late_offset(low_tail_state)
    if voice_ended and echo_enabled and envelope_moving:
        back_phase = (best_phase - 1) & 0x0F
        back_key, back_state = candidates[back_phase]
        if _should_backstep_ended_moving_echo_phase(
            best_phase=best_phase,
            best_error=best_key[0],
            back_error=back_key[0],
            best_buf12=best_state[1],
            back_buf12=back_state[1],
            echo_enabled=echo_enabled,
            envelope_moving=envelope_moving,
            voice_ended=voice_ended,
        ):
            _trace("phase_rule", rule_id="R3",
                   srcn=srcn, pitch=pitch,
                   best_phase=best_phase, back_phase=back_phase)
            return with_late_offset(back_state)
    if voice_ended and (best_phase & 0x03) == 0:
        back_phase = (best_phase - 1) & 0x0F
        back_key, back_state = candidates[back_phase]
        back_transition = _window_transition_energy(back_state[1])
        if _should_backstep_quartet_boundary_phase(
            best_phase=best_phase,
            best_error=best_key[0],
            best_transition=best_transition,
            back_error=back_key[0],
            back_transition=back_transition,
            voice_ended=voice_ended,
            envelope_moving=envelope_moving,
        ):
            _trace("phase_rule", rule_id="R7",
                   srcn=srcn, pitch=pitch,
                   best_phase=best_phase, back_phase=back_phase)
            return with_late_offset(back_state)
    if (
        not echo_enabled
        and envelope_moving
        and not voice_ended
        and 0x08 <= saved_phase <= 0x0B
        and 0x08 <= best_phase <= 0x0B
    ):
        back_phase = (saved_phase - 3) & 0x0F
        back_key, back_state = candidates[back_phase]
        if _should_backstep_dry_moving_high_volume_phase(
            saved_phase=saved_phase,
            best_phase=best_phase,
            best_error=best_key[0],
            back_error=back_key[0],
            best_buf12=best_state[1],
            back_buf12=back_state[1],
            echo_enabled=echo_enabled,
            envelope_moving=envelope_moving,
            voice_ended=voice_ended,
            voice_volume_sum=voice_volume_sum,
        ):
            _trace("phase_rule", rule_id="R8",
                   srcn=srcn, pitch=pitch,
                   best_phase=best_phase, saved_phase=saved_phase,
                   back_phase=back_phase, voice_volume_sum=voice_volume_sum)
            return with_late_offset(back_state)

    if saved_state is not None and saved_key is not None:
        tail_phase = (saved_phase - 9) & 0x0F
        tail_key, tail_state = candidates[tail_phase]
        if _should_use_dry_ended_tail_phase(
            saved_phase=saved_phase,
            best_phase=best_phase,
            best_error=best_key[0],
            tail_error=tail_key[0],
            tail_buf12=tail_state[1],
            echo_enabled=echo_enabled,
            envelope_moving=envelope_moving,
            voice_ended=voice_ended,
            voice_volume_sum=voice_volume_sum,
            env=env,
        ):
            _trace("phase_rule", rule_id="R10",
                   srcn=srcn, pitch=pitch,
                   best_phase=best_phase, saved_phase=saved_phase,
                   tail_phase=tail_phase, env=env)
            return with_late_offset(tail_state)

    # Echo voices whose envelope is actively moving can serialize an out_sample
    # from just after the quartet wrap. When the numeric match lands in the last
    # quartet, phase 0 is often the stable continuation point for Blargg.
    if echo_enabled and envelope_moving and not voice_ended and best_phase >= 0x0C:
        wrap_key, wrap_state = candidates[0]
        if wrap_key[0] <= max(best_key[0] + 1200, best_key[0] * 4 + 1):
            return with_late_offset(wrap_state)

    # In paired/echoed samples, an ended companion can make the live echo voice's
    # saved phase more trustworthy than a one-sample out_sample match.
    if echo_enabled and same_srcn_ended_peer and not voice_ended and saved_state is not None:
        assert saved_key is not None
        prev_phase = (saved_phase - 1) & 0x0F
        prev_key, prev_state = candidates[prev_phase]
        if _should_backstep_live_echo_peer_phase(
            saved_error=saved_key[0],
            prev_error=prev_key[0],
            saved_buf12=saved_state[1],
            prev_buf12=prev_state[1],
            echo_enabled=echo_enabled,
            envelope_moving=envelope_moving,
            voice_ended=voice_ended,
            same_srcn_ended_peer=same_srcn_ended_peer,
        ):
            _trace("phase_rule", rule_id="R4",
                   srcn=srcn, pitch=pitch,
                   saved_phase=saved_phase, prev_phase=prev_phase)
            return with_late_offset(prev_state)
        if saved_key[0] <= max(best_key[0] + 5000, best_key[0] * 16 + 1):
            return with_late_offset(saved_state)

    # Finally, if one phase produces a dramatically smoother first BRR window
    # than the out_sample winner, take the smooth window. This is intentionally
    # guarded by both total transition and max-step ratios so ordinary vibrato or
    # percussion attacks are still anchored by the saved output sample.
    if best_max_step >= 3000 and not (echo_enabled and envelope_moving):
        smooth_pool = []
        for key, state in candidates.values():
            transition = _window_transition_energy(state[1])
            max_step = _window_max_step(state[1])
            if (
                key[0] <= _smooth_phase_error_limit(best_key[0])
                and transition * 100 <= best_transition * 50
                and max_step * 100 <= best_max_step * 65
            ):
                smooth_pool.append((key[0], transition, max_step, key[1], state))
        if smooth_pool:
            smooth_pool.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
            chosen_key_error, _transition, _max_step, _distance, chosen_state = smooth_pool[0]
            back_phase = (chosen_state[0] - 4) & 0x0F
            back_key, back_state = candidates[back_phase]
            if _should_backstep_smooth_echo_cluster_phase(
                saved_phase=saved_phase,
                chosen_phase=chosen_state[0],
                chosen_error=chosen_key_error,
                back_error=back_key[0],
                chosen_buf12=chosen_state[1],
                back_buf12=back_state[1],
                echo_enabled=echo_enabled,
                envelope_moving=envelope_moving,
                voice_ended=voice_ended,
                same_srcn_active_count=same_srcn_active_count,
            ):
                _trace("phase_rule", rule_id="R5",
                       srcn=srcn, pitch=pitch,
                       chosen_phase=chosen_state[0],
                       saved_phase=saved_phase,
                       back_phase=back_phase)
                return with_late_offset(back_state)
            return with_late_offset(chosen_state)
    return with_late_offset(best_state)
