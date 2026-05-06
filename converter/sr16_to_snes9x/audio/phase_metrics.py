"""Small metrics used by first-frame SSZ phase selection."""
from __future__ import annotations

def _sample_ptr_distance(a: int, b: int) -> int:
    """Small cyclic distance between two 4-bit sample pointers."""
    diff = abs((a & 0x0F) - (b & 0x0F))
    return min(diff, 16 - diff)

def _window_transition_energy(buf12: list[int]) -> int:
    """Return a small roughness score for the first samples in a voice window."""
    limit = min(len(buf12) - 1, 7)
    if limit <= 0:
        return 0
    return sum(abs(int(buf12[i + 1]) - int(buf12[i])) for i in range(limit))

def _window_max_step(buf12: list[int]) -> int:
    """Return the largest early sample-to-sample jump in a voice window."""
    limit = min(len(buf12) - 1, 7)
    if limit <= 0:
        return 0
    return max(abs(int(buf12[i + 1]) - int(buf12[i])) for i in range(limit))

def _smooth_phase_error_limit(best_error: int) -> int:
    """Maximum saved-output error allowed for the smooth-window fallback.

    The smooth fallback is only a tie-breaker for ambiguous BRR phase choices.
    If it is allowed to ignore SR16's saved output sample too freely, it can
    choose a visually smooth decoded window whose first actual DSP output is a
    wrong note/pop. Keep the limit relative to the best one-sample match while
    still allowing the older Super Metroid edge cases that needed this path.
    """
    return max(best_error + 3500, best_error * 3 + 1, 1400)
