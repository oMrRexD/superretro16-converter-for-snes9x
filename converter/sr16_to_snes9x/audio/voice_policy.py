"""SR16 SSZ voice resume and echo-buffer policy helpers.

Mask-rule index for ``_quiet_duplicate_ssz_voice_mask``. Each rule below
identifies a "stale tail" voice shape that produced a first-frame artifact
in the calibration set. Editing any guard requires re-running the audio
regression suite — these thresholds were tuned empirically and a single
loosened bound has historically broken at least one other save.

  M1 stale_tiny_echo
       Source: calibration set audits (low-SRCN echo peers).
       Intent: silence near-silent companion echo voices when a same-SRCN
       louder voice is already carrying the instrument.

  M2 stale_echo_with_dry_anchor
       Source: A Link to the Past s34 audio probe.
       Intent: very-low-volume echo voice paired with a much louder dry
       peer of the same sample.

  M3 stale_ended_echo_with_dry_peer
       Source: Final Fantasy V battle clusters.
       Intent: ENDX-latched echo voice in a same-SRCN cluster of >= 3
       voices where a dry peer is meaningfully louder.

  M4 stale_low_srcn_sfx_tail
       Source: Super Metroid SFX tails.
       Intent: dry low-SRCN SFX-shape voice carried while music has a
       strong echo bed; SR16 may keep it active but Blargg pops on resume.

  M5 stale_ended_echo_peer_tail
       Source: Chrono Trigger battle echoes.
       Intent: ENDX-latched echo voice in a >= 3-voice same-SRCN cluster
       with a much louder peer.

  M6 stale_tiny_ended_dry_peer
       Source: Mega Man X3 saves.
       Intent: ENDX-latched dry voice with vol_sum <= 4 in a >= 4-voice
       cluster where a louder dry peer carries the actual instrument.

  M7 stale_live_echo_cluster_lead
       Source: Donkey Kong Country zelda-s34 audio fix probe.
       Intent: live-moving low-SRCN echo voice that is the lone non-ended
       member of a >= 6-voice all-echo same-SRCN cluster — Blargg can
       crackle on its first frame.
"""
from __future__ import annotations

from converter.common._trace import trace as _trace

def _should_resume_ssz_voice(active: bool, uses_noise: bool) -> bool:
    """Return whether a voice should be deep-resumed from SSZ."""
    return active

def _s8(value: int) -> int:
    """Interpret an unsigned byte as a signed DSP volume."""
    value &= 0xFF
    return value - 0x100 if value & 0x80 else value

def _quiet_duplicate_ssz_voice_mask(ssz: bytes, dsp_regs: bytes, keyed: int) -> int:
    """Find near-silent duplicate voices that should not be deep-resumed.

    Some old SoundData snapshots keep a very quiet companion voice active while
    a louder voice with the same sample is already carrying the instrument. SR16
    tolerates that stale tail, but Blargg can turn its seeded first buffer into a
    faint one-frame artifact. Leave those tiny companions silent at load; the SPC
    music driver can update or re-key them normally afterward.
    """
    if len(ssz) < 1281:
        return 0

    voices: list[dict[str, int | bool]] = []
    loudest_by_srcn: dict[int, int] = {}
    loudest_dry_by_srcn: dict[int, int] = {}
    active_count_by_srcn: dict[int, int] = {}
    ended_count_by_srcn: dict[int, int] = {}
    echo_count_by_srcn: dict[int, int] = {}

    for voice in range(8):
        base = 0x30 + voice * 0x75
        ext = 0x3DC + voice * 0x22
        state = int.from_bytes(ssz[base:base + 4], "big")
        old_env = int.from_bytes(ssz[ext + 0x02:ext + 0x06], "big")
        if old_env == 0:
            old_env = int.from_bytes(ssz[base + 0x15:base + 0x19], "big") << 4
        env = max(0, min(0x7FF, old_env))
        active = state != 0 and bool(keyed & (1 << voice)) and env > 0
        srcn = dsp_regs[voice * 0x10 + 0x04]
        vol_sum = abs(_s8(dsp_regs[voice * 0x10 + 0x00]))
        vol_sum += abs(_s8(dsp_regs[voice * 0x10 + 0x01]))

        resume_candidate = _should_resume_ssz_voice(
            active, bool(dsp_regs[0x3D] & (1 << voice))
        )
        voices.append({
            "voice": voice,
            "srcn": srcn,
            "vol_sum": vol_sum,
            "resume": resume_candidate,
            "echo": bool(dsp_regs[0x4D] & (1 << voice)),
            "ended": bool(dsp_regs[0x7C] & (1 << voice)),
            "moving": bool(
                int.from_bytes(ssz[base + 0x23:base + 0x27], "big")
                or int.from_bytes(ssz[ext + 0x0E:ext + 0x12], "big")
            ),
            "low_srcn": srcn < 0x10,
        })
        if resume_candidate:
            loudest_by_srcn[srcn] = max(loudest_by_srcn.get(srcn, 0), vol_sum)
            active_count_by_srcn[srcn] = active_count_by_srcn.get(srcn, 0) + 1
            if bool(dsp_regs[0x7C] & (1 << voice)):
                ended_count_by_srcn[srcn] = ended_count_by_srcn.get(srcn, 0) + 1
            if bool(dsp_regs[0x4D] & (1 << voice)):
                echo_count_by_srcn[srcn] = echo_count_by_srcn.get(srcn, 0) + 1
            else:
                loudest_dry_by_srcn[srcn] = max(
                    loudest_dry_by_srcn.get(srcn, 0), vol_sum
                )

    mask = 0
    active_count = sum(1 for meta in voices if meta["resume"])
    has_strong_echo_bed = any(
        bool(meta["resume"]) and bool(meta["echo"]) and int(meta["vol_sum"]) >= 80
        for meta in voices
    )
    for meta in voices:
        srcn = int(meta["srcn"])
        louder_peer = loudest_by_srcn.get(srcn, 0)
        if meta["echo"]:
            louder_peer = loudest_dry_by_srcn.get(srcn, 0)
        if not meta["resume"]:
            continue

        vol_sum = int(meta["vol_sum"])
        same_srcn_loudest = loudest_by_srcn.get(srcn, 0)
        same_srcn_count = active_count_by_srcn.get(srcn, 0)
        same_srcn_ended_count = ended_count_by_srcn.get(srcn, 0)
        same_srcn_echo_count = echo_count_by_srcn.get(srcn, 0)
        stale_tiny_echo = (
            meta["echo"]
            and active_count > 1
            and vol_sum <= 5
            and same_srcn_loudest <= 5
        )
        stale_echo_with_dry_anchor = (
            meta["echo"]
            and vol_sum <= 10
            and louder_peer >= max(8, vol_sum * 3)
        )
        dry_peer = loudest_dry_by_srcn.get(srcn, 0)
        stale_ended_echo_with_dry_peer = (
            meta["echo"]
            and meta["ended"]
            and dry_peer > 0
            and (
                (
                    same_srcn_count >= 4
                    and vol_sum <= 32
                    and dry_peer * 5 >= vol_sum * 4
                )
                or (
                    same_srcn_count >= 3
                    and vol_sum >= 32
                    and dry_peer >= 12
                    and vol_sum * 2 >= dry_peer * 3
                )
            )
        )
        stale_low_srcn_sfx_tail = (
            not meta["echo"]
            and bool(meta["low_srcn"])
            and vol_sum <= 60
            and active_count <= 3
            and has_strong_echo_bed
        )
        stale_ended_echo_peer_tail = (
            meta["echo"]
            and meta["ended"]
            and same_srcn_count >= 3
            and vol_sum <= 20
            and same_srcn_loudest >= max(24, vol_sum * 3)
        )
        stale_tiny_ended_dry_peer = (
            not meta["echo"]
            and meta["ended"]
            and same_srcn_count >= 4
            and vol_sum <= 4
            and dry_peer >= max(12, vol_sum * 5)
        )
        stale_live_echo_cluster_lead = (
            meta["echo"]
            and not meta["ended"]
            and meta["moving"]
            and srcn < 0x10
            and same_srcn_count >= 6
            and same_srcn_echo_count == same_srcn_count
            and dry_peer == 0
            and same_srcn_ended_count >= same_srcn_count - 1
            and vol_sum >= 32
            and vol_sum == same_srcn_loudest
        )
        fired = []
        if stale_tiny_echo: fired.append("M1")
        if stale_echo_with_dry_anchor: fired.append("M2")
        if stale_ended_echo_with_dry_peer: fired.append("M3")
        if stale_low_srcn_sfx_tail: fired.append("M4")
        if stale_ended_echo_peer_tail: fired.append("M5")
        if stale_tiny_ended_dry_peer: fired.append("M6")
        if stale_live_echo_cluster_lead: fired.append("M7")
        if fired:
            _trace("voice_policy_mask",
                   voice=int(meta["voice"]),
                   srcn=srcn,
                   vol_sum=vol_sum,
                   same_srcn_count=same_srcn_count,
                   rule_ids=",".join(fired))
            mask |= 1 << int(meta["voice"])
    return mask

def _zero_circular_region(buf: bytearray, start: int, count: int) -> None:
    """Zero `count` bytes in 64K SPC RAM, wrapping at the address boundary."""
    if not buf or count <= 0:
        return
    for i in range(count):
        buf[(start + i) & 0xFFFF] = 0

def _clear_initial_echo_buffer(ram: bytearray, dsp_regs: bytearray) -> None:
    """Clear saved echo history while preserving echo DSP registers."""
    echo_base = (dsp_regs[0x6D] << 8) & 0xFFFF
    echo_len = (dsp_regs[0x7D] & 0x0F) * 0x800
    if echo_len:
        _zero_circular_region(ram, echo_base, echo_len)


# --- BRR / Gauss interpolation -------------------------------------------
