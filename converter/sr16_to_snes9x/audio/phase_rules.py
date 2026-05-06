"""Decision rules for first-frame SSZ voice phase selection.

Rule index (each function below is one rule, R<n>). The "Source" line names
the calibration save the rule was originally cut against — that's the most
likely save to surface a regression if a guard is changed. Rules are
**guard-only**: they neither read nor mutate global state, and they have no
side effects beyond returning a bool/Optional decision. Tracing of which
rule actually fires happens in ``phase_calibration.py`` when ``CONVERTER_TRACE``
is set; nothing is logged at decision time inside this file.

Editing policy: do **not** loosen or extend any guard without re-running
the internal regression harness against the audio calibration set. These
thresholds were tuned empirically; widening one in isolation typically
breaks at least one other save in the audio test matrix.

  R1  _should_prefer_saved_sample_ptr_phase
       Source: SSZ first-frame texture audits across calibration set.
       Intent: when one-sample match and saved-pointer match disagree but the
       output-best phase produces a rough first BRR window, trust SR16's
       serialized phase.

  R2  _should_prefer_saved_echo_wrap_phase
       Source: Chrono Trigger battle/scene saves (SSZ s03/s29/s43).
       Intent: moving-echo voices whose "best" lands at quartet 8..B while
       SR16 saved C..F — taking the numeric match advances Blargg one quartet
       early and creates first-frame harshness.

  R3  _should_backstep_ended_moving_echo_phase
       Source: Chrono Trigger ENDX-latched echo voices.
       Intent: ENDX-latched + envelope-still-moving echo voices saved while
       Blargg's best one-sample match landed at the very tail of the quartet;
       back up one phase if the neighbor stays plausible.

  R4  _should_backstep_live_echo_peer_phase
       Source: Chrono Trigger live echo amid ended same-SRCN peers.
       Intent: live echo voice with already-ended same-sample peers; saved
       phase is sometimes one DSP phase late.

  R5  _should_backstep_smooth_echo_cluster_phase
       Source: Chrono Trigger clustered echo voices.
       Intent: smooth fallback may pick the next BRR quartet because it has
       a slightly better one-sample match; prefer the previous quartet when
       it is closer to SR16's saved phase with comparable roughness.

  R6  _should_backstep_low_srcn_live_tail_phase
       Source: Super Metroid SFX tails.
       Intent: low-SRCN dry voice produces an excellent one-sample match
       exactly one quartet ahead of SR16's saved phase, but that jump
       creates a first-frame tick.

  R7  _should_backstep_quartet_boundary_phase
       Source: Static ENDX tails (calibration set).
       Intent: ENDX tail that landed one phase too late at a quartet boundary.

  R8  _should_backstep_dry_moving_high_volume_phase
       Source: Loud dry moving voices (calibration set).
       Intent: loud dry moving voice resumed one quartet too late.

  R9  _should_prefer_static_echo_saved_phase
       Source: Live static echo voices near quartet wrap.
       Intent: live static echo voice saved near quartet wrap; saved phase
       is the safer continuation point.

  R10 _should_use_dry_ended_tail_phase
       Source: Dry ENDX tails (calibration set).
       Intent: loud dry ENDX tail whose exact match clicks; use the
       phase-9 backstep.

  R11 _forced_first_frame_tail_phase  (multiple sub-cases R11a..R11i below)
       Source: SSZ stale-tail audits (Chrono Trigger / ALTTP / Super Metroid).
       Intent: narrow phase/offset overrides for old-SoundData tails whose
       hidden voice tail is one or more quartet windows away from Blargg's
       continuation. Each sub-case is keyed on a precise (srcn, pitch, vol,
       env, echo, ended, envelope_moving, saved_phase) shape.

  R12 _should_use_late_brr_decode_offset
       Source: Multi-voice echo clusters (Chrono Trigger / ALTTP).
       Intent: late BRR decode offset for echo/voice clusters in narrow
       pitch/phase windows.
"""
from __future__ import annotations

from .phase_metrics import (
    _sample_ptr_distance,
    _window_max_step,
    _window_transition_energy,
)

def _should_prefer_saved_sample_ptr_phase(
    *,
    sample_distance: int,
    best_error: int,
    saved_error: int,
    best_buf12: list[int],
    saved_buf12: list[int],
) -> bool:
    """Return True when the saved SSZ phase is safer than the output-matched one.

    Old SoundData has both a current sample pointer and one saved output sample.
    Usually the output sample is the best anchor, but occasionally several
    phases can match that one sample while producing a rough first BRR window.
    In that case, prefer the phase SR16 actually serialized.
    """
    best_transition = _window_transition_energy(best_buf12)
    saved_transition = _window_transition_energy(saved_buf12)
    best_max_step = _window_max_step(best_buf12)

    if (
        saved_error <= 768
        and saved_transition * 100 <= best_transition * 35
        and (best_transition >= 12000 or best_max_step >= 6000)
    ):
        return True

    if sample_distance < 4:
        return False

    improvement = int(saved_error) - int(best_error)
    if improvement >= 2000 and saved_transition * 100 <= best_transition * 85:
        return True

    return saved_error <= 1600 and saved_transition * 100 <= best_transition * 80

def _should_prefer_saved_echo_wrap_phase(
    *,
    best_phase: int,
    saved_phase: int,
    best_error: int,
    saved_error: int,
    best_buf12: list[int],
    saved_buf12: list[int],
    echo_enabled: bool,
    envelope_moving: bool,
    voice_ended: bool,
) -> bool:
    """Return True for an old-SoundData quartet-wrap continuation quirk.

    For moving echo voices, the single serialized `out_sample` can match best
    in phase 8..B while the saved SoundData phase is already in C..F. Taking
    the numeric match there advances Blargg's next BRR decode one quartet early,
    which creates a harsh first-frame texture in Chrono Trigger. If SR16's
    saved C..F phase is still a close match and not wildly rough, trust it.
    """
    if not (echo_enabled and envelope_moving) or voice_ended:
        return False
    if not (0x08 <= best_phase <= 0x0B and saved_phase >= 0x0C):
        return False
    if saved_error > max(best_error + 1600, best_error * 4 + 1):
        return False

    best_transition = _window_transition_energy(best_buf12)
    saved_transition = _window_transition_energy(saved_buf12)
    best_max_step = _window_max_step(best_buf12)
    saved_max_step = _window_max_step(saved_buf12)
    return (
        saved_transition <= max(12000, best_transition * 3)
        and saved_max_step <= max(3500, best_max_step * 4)
    )

def _should_backstep_ended_moving_echo_phase(
    *,
    best_phase: int,
    best_error: int,
    back_error: int,
    best_buf12: list[int],
    back_buf12: list[int],
    echo_enabled: bool,
    envelope_moving: bool,
    voice_ended: bool,
) -> bool:
    """Return True when an ended moving echo voice is one phase too late.

    ENDX-latched echo voices saved while their envelope is still moving are a
    real state in old SoundData: SR16 continues them smoothly, but Blargg can
    make the most accurate one-sample match land at the very tail of the
    quartet. Back up one phase when the neighboring phase remains plausible and
    no roughness is introduced.
    """
    if not (voice_ended and echo_enabled and envelope_moving):
        return False
    if best_phase < 0x0E:
        return False
    if back_error > best_error + 3500:
        return False

    best_transition = _window_transition_energy(best_buf12)
    back_transition = _window_transition_energy(back_buf12)
    best_max_step = _window_max_step(best_buf12)
    back_max_step = _window_max_step(back_buf12)
    return (
        back_transition <= max(best_transition * 2, 1)
        and back_max_step <= max(best_max_step, 8000)
    )

def _should_backstep_live_echo_peer_phase(
    *,
    saved_error: int,
    prev_error: int,
    saved_buf12: list[int],
    prev_buf12: list[int],
    echo_enabled: bool,
    envelope_moving: bool,
    voice_ended: bool,
    same_srcn_ended_peer: bool,
) -> bool:
    """Return True when a live echo peer serialized one phase late.

    Old SoundData can save a still-live echo voice among several already-ended
    peers of the same sample. In that layout the saved phase is useful, but
    sometimes it is one DSP phase late; the immediately previous phase has the
    same BRR window roughness and a much better saved output match.
    """
    if not (echo_enabled and envelope_moving and same_srcn_ended_peer):
        return False
    if voice_ended:
        return False
    if prev_error > max(512, saved_error // 3):
        return False

    saved_transition = _window_transition_energy(saved_buf12)
    prev_transition = _window_transition_energy(prev_buf12)
    saved_max_step = _window_max_step(saved_buf12)
    prev_max_step = _window_max_step(prev_buf12)
    return (
        prev_transition <= max(saved_transition * 2, 1)
        and prev_max_step <= max(saved_max_step * 2, 1)
    )

def _should_backstep_smooth_echo_cluster_phase(
    *,
    saved_phase: int,
    chosen_phase: int,
    chosen_error: int,
    back_error: int,
    chosen_buf12: list[int],
    back_buf12: list[int],
    echo_enabled: bool,
    envelope_moving: bool,
    voice_ended: bool,
    same_srcn_active_count: int,
) -> bool:
    """Return True when smooth fallback jumped one quartet too far.

    For clustered echo voices with the same sample, the smooth fallback may
    pick the next BRR quartet because it has a slightly better one-sample
    match. If the previous quartet is much closer to SR16's saved phase and has
    comparable roughness, use it instead.
    """
    if not (echo_enabled and not envelope_moving and not voice_ended):
        return False
    if same_srcn_active_count < 3:
        return False
    if _sample_ptr_distance(chosen_phase, saved_phase) < 6:
        return False
    if _sample_ptr_distance((chosen_phase - 4) & 0x0F, saved_phase) >= (
        _sample_ptr_distance(chosen_phase, saved_phase)
    ):
        return False
    if back_error > chosen_error + 1200:
        return False

    chosen_transition = _window_transition_energy(chosen_buf12)
    back_transition = _window_transition_energy(back_buf12)
    chosen_max_step = _window_max_step(chosen_buf12)
    back_max_step = _window_max_step(back_buf12)
    return (
        back_transition * 100 <= max(chosen_transition * 125, 1)
        and back_max_step <= max(chosen_max_step * 2, 1)
    )

def _should_backstep_low_srcn_live_tail_phase(
    *,
    saved_phase: int,
    best_phase: int,
    best_error: int,
    low_srcn_voice: bool,
    echo_enabled: bool,
    envelope_moving: bool,
    voice_ended: bool,
) -> bool:
    """Return True for a tiny dry SFX-tail phase advance.

    A low-SRCN dry voice can produce an excellent one-sample match exactly one
    quartet ahead of SR16's saved phase, but that jump creates a first-frame
    tick. The shape is intentionally narrow and only applies to live, static,
    non-echo voices.
    """
    return (
        low_srcn_voice
        and not echo_enabled
        and not envelope_moving
        and not voice_ended
        and best_error <= 256
        and best_phase == ((saved_phase + 4) & 0x0F)
    )

def _should_backstep_quartet_boundary_phase(
    *,
    best_phase: int,
    best_error: int,
    best_transition: int,
    back_error: int,
    back_transition: int,
    voice_ended: bool,
    envelope_moving: bool,
) -> bool:
    """Return True for a static ENDX tail that landed one phase too late."""
    return (
        voice_ended
        and not envelope_moving
        and (best_phase & 0x03) == 0
        and (best_transition >= 9000 or best_error >= 512)
        and (best_error >= 512 or back_transition <= best_transition)
        and back_transition <= best_transition * 2
        and back_error <= max(best_error + 7000, best_error * 8 + 1)
    )

def _should_backstep_dry_moving_high_volume_phase(
    *,
    saved_phase: int,
    best_phase: int,
    best_error: int,
    back_error: int,
    best_buf12: list[int],
    back_buf12: list[int],
    echo_enabled: bool,
    envelope_moving: bool,
    voice_ended: bool,
    voice_volume_sum: int,
) -> bool:
    """Return True when a loud dry moving voice resumed one quartet too late."""
    if echo_enabled or not envelope_moving or voice_ended:
        return False
    if voice_volume_sum < 128:
        return False
    if not (0x08 <= saved_phase <= 0x0B and 0x08 <= best_phase <= 0x0B):
        return False
    if back_error > max(best_error + 1200, best_error * 4 + 1):
        return False

    best_transition = _window_transition_energy(best_buf12)
    back_transition = _window_transition_energy(back_buf12)
    best_max_step = _window_max_step(best_buf12)
    back_max_step = _window_max_step(back_buf12)
    return (
        back_transition * 100 <= max(best_transition * 65, 1)
        and back_max_step * 100 <= max(best_max_step * 80, 1)
    )

def _should_prefer_static_echo_saved_phase(
    *,
    saved_phase: int,
    best_phase: int,
    best_error: int,
    saved_error: int,
    best_buf12: list[int],
    saved_buf12: list[int],
    echo_enabled: bool,
    envelope_moving: bool,
    voice_ended: bool,
    voice_volume_sum: int,
) -> bool:
    """Return True for a live static echo voice saved near quartet wrap."""
    if not (echo_enabled and not envelope_moving and not voice_ended):
        return False
    if voice_volume_sum > 60:
        return False
    if saved_phase < 0x0C or not (0x08 <= best_phase <= 0x0C):
        return False
    if saved_error > max(best_error + 7000, best_error * 20 + 1):
        return False

    best_transition = _window_transition_energy(best_buf12)
    saved_transition = _window_transition_energy(saved_buf12)
    best_max_step = _window_max_step(best_buf12)
    saved_max_step = _window_max_step(saved_buf12)
    return (
        saved_transition <= max(32000, best_transition * 4)
        and saved_max_step <= max(9000, best_max_step * 4)
    )

def _should_use_dry_ended_tail_phase(
    *,
    saved_phase: int,
    best_phase: int,
    best_error: int,
    tail_error: int,
    tail_buf12: list[int],
    echo_enabled: bool,
    envelope_moving: bool,
    voice_ended: bool,
    voice_volume_sum: int,
    env: int,
) -> bool:
    """Return True for a loud dry ENDX tail whose exact match clicks."""
    if echo_enabled or envelope_moving or not voice_ended:
        return False
    if env < 0x700 or voice_volume_sum < 45:
        return False
    if saved_phase < 0x0D or best_phase < 0x08:
        return False
    if tail_error > max(best_error + 28000, 30000):
        return False
    return _window_max_step(tail_buf12) <= 9000

def _forced_first_frame_tail_phase(
    *,
    saved_phase: int,
    pitch: int,
    env: int,
    echo_enabled: bool,
    envelope_moving: bool,
    voice_ended: bool,
    voice_volume_sum: int,
    low_srcn_voice: bool,
    srcn: int,
) -> tuple[int, int] | None:
    """Return a narrow phase/offset override for stale old-SoundData tails.

    These cases are not ordinary phase ambiguities: the old SR16/Snes9x
    SoundData has a plausible output sample, but its hidden voice tail is one
    or more quartet windows away from the continuation Blargg expects. Using
    only the one-sample match leaves a first-frame burst. Keep the guards tied
    to DSP shape instead of ROM names so legitimate sustained instruments keep
    following the normal calibrator.
    """
    saved_phase &= 0x0F
    pitch &= 0x3FFF

    if echo_enabled and voice_ended and not envelope_moving and env >= 0x700:
        high_pitch_low_srcn_echo_tail = (
            low_srcn_voice
            and voice_volume_sum <= 24
            and pitch >= 0x2000
            and 0x08 <= saved_phase <= 0x0B
        )
        if high_pitch_low_srcn_echo_tail:
            return ((saved_phase - 6) & 0x0F, 3)

        low_volume_mid_pitch_tail = (
            voice_volume_sum <= 24
            and 0x0E00 <= pitch <= 0x1000
        )
        if low_volume_mid_pitch_tail:
            if saved_phase >= 0x0E:
                return ((saved_phase - 0x0C) & 0x0F, 3)
            return ((saved_phase - 3) & 0x0F, 3)

        high_sample_zero_tail = (
            srcn >= 0x28
            and 30 <= voice_volume_sum <= 45
            and saved_phase <= 1
            and 0x1300 <= pitch <= 0x1700
        )
        if high_sample_zero_tail:
            return ((saved_phase + 4) & 0x0F, 1)

    if (
        not echo_enabled
        and voice_ended
        and not envelope_moving
        # Quiet dry tail following a fully-ended Super Metroid title echo
        # cluster.  Muting loses an instrument; phase 4/offset 3 keeps it
        # audible while matching SR16's first-frame texture.
        and env >= 0x700
        and 0x18 <= srcn <= 0x1F
        and 24 <= voice_volume_sum <= 32
        and 0x0200 <= pitch <= 0x0400
        and saved_phase == 0x0C
    ):
        return (4, 3)

    if (
        not echo_enabled
        and voice_ended
        and not envelope_moving
        and srcn >= 0x28
        and 30 <= voice_volume_sum <= 45
        and 0x0C00 <= pitch <= 0x1000
        and saved_phase >= 0x0C
    ):
        return (4, 3)

    if echo_enabled and not voice_ended and not envelope_moving:
        high_pitch_live_echo_tail = (
            voice_volume_sum >= 25
            and pitch >= 0x2400
            and 4 <= saved_phase <= 7
        )
        if high_pitch_live_echo_tail:
            return ((saved_phase + 5) & 0x0F, 5)

        mid_pitch_live_echo_tail = (
            25 <= voice_volume_sum <= 40
            and 0x1800 <= pitch <= 0x2200
            and saved_phase >= 0x0C
        )
        if mid_pitch_live_echo_tail:
            return ((saved_phase - 2) & 0x0F, 5)

    if (
        not echo_enabled
        and voice_ended
        and envelope_moving
        and low_srcn_voice
        and voice_volume_sum >= 64
        and pitch >= 0x1800
        and saved_phase >= 8
    ):
        return ((saved_phase + 7) & 0x0F, 3)

    if (
        echo_enabled
        and voice_ended
        and envelope_moving
        and 20 <= voice_volume_sum <= 35
        and srcn >= 0x28
    ):
        if pitch >= 0x1800 and saved_phase >= 8:
            return ((saved_phase + 6) & 0x0F, 3)
        if 0x1200 <= pitch <= 0x1600 and 5 <= saved_phase <= 7:
            return ((saved_phase + 4) & 0x0F, 7)

    if echo_enabled and voice_ended and envelope_moving:
        if (
            srcn <= 0x1F
            and voice_volume_sum <= 24
            and 0x0E00 <= pitch <= 0x1000
            and saved_phase >= 0x0E
        ):
            return ((saved_phase - 0x0C) & 0x0F, 3)
        if (
            0x20 <= srcn <= 0x25
            and voice_volume_sum >= 45
            and pitch <= 0x0400
            and 4 <= saved_phase <= 6
        ):
            return (0, 3)

    if not echo_enabled and voice_ended and envelope_moving:
        if (
            srcn >= 0x28
            and 30 <= voice_volume_sum <= 45
            and 0x0C00 <= pitch <= 0x1000
            and saved_phase >= 0x0C
        ):
            return (4, 3)
        if (
            srcn < 0x20
            and env >= 0x700
            and voice_volume_sum >= 64
            and pitch <= 0x0800
            and saved_phase >= 0x0A
        ):
            return ((saved_phase - 0x0A) & 0x0F, 3)

    return None

def _should_use_late_brr_decode_offset(
    *,
    saved_phase: int,
    chosen_phase: int,
    current_offset: int,
    voice_volume_sum: int,
    srcn: int,
    same_srcn_active_count: int,
    echo_enabled: bool,
    envelope_moving: bool,
    voice_ended: bool,
) -> bool:
    """Return True when Blargg should resume at a later BRR byte offset.

    Phase selection controls the already-seeded interpolation buffer. The next
    BRR decode is separate: a valid buffer can still point Blargg at offset 1/3
    when SR16's old pipeline was effectively going to consume bytes 5/7 next.
    Use offset 5 only for narrow non-muted shapes confirmed by listening tests,
    avoiding the older broad offset cap regression.
    """
    if current_offset not in (1, 3):
        return False
    echo_tail_continuation = (
        echo_enabled
        and current_offset in (1, 3)
        and voice_volume_sum >= 20
        and (
            voice_ended
            or (envelope_moving and saved_phase >= 0x08)
        )
    )
    if echo_tail_continuation:
        return True
    if envelope_moving:
        return False

    static_live_echo_mid_block = (
        echo_enabled
        and not voice_ended
        and current_offset == 3
        and 4 <= saved_phase <= 7
        and 4 <= chosen_phase <= 7
        and voice_volume_sum >= 20
    )
    high_srcn_ended_dry_cluster = (
        not echo_enabled
        and voice_ended
        and current_offset == 1
        and srcn >= 0x20
        and same_srcn_active_count >= 2
        and voice_volume_sum >= 20
    )
    high_phase_live_dry_pair = (
        not echo_enabled
        and not voice_ended
        and current_offset == 3
        and saved_phase >= 0x0C
        and same_srcn_active_count >= 2
        and voice_volume_sum <= 45
    )
    static_live_echo_next_block = (
        echo_enabled
        and not voice_ended
        and not envelope_moving
        and current_offset == 1
        and 4 <= saved_phase <= 7
        and 8 <= chosen_phase <= 0x0B
        and voice_volume_sum >= 20
    )
    return (
        static_live_echo_mid_block
        or high_srcn_ended_dry_cluster
        or high_phase_live_dry_pair
        or static_live_echo_next_block
    )
