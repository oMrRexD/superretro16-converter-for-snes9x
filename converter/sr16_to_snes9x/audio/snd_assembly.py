"""Final SND chunk assembly helpers."""
from __future__ import annotations

from converter.common.constants import (
    SNES_SND_SIZE, SR16_AR1_SIZE, SND_SMP_BYTES, SND_DSP_BYTES, SND_TAIL_BYTES,
)

def _assemble_snd(ram: bytes, smp: bytes, dsp: bytes,
                  cpu_to_smp_ports: bytes) -> bytes:
    """Concatenate the four SND regions and zero-pad to SNES_SND_SIZE."""
    tail = bytearray(SND_TAIL_BYTES)  # scheduler fields stay zero
    tail[12:16] = cpu_to_smp_ports
    body = bytes(ram) + bytes(smp) + bytes(dsp) + bytes(tail)
    expected = SR16_AR1_SIZE + SND_SMP_BYTES + SND_DSP_BYTES + SND_TAIL_BYTES
    assert len(body) == expected, f"SND body size {len(body)}, expected {expected}"
    return body + b"\x00" * (SNES_SND_SIZE - len(body))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _default_ctl() -> bytes:
    """Build a safe default CTL chunk (91 bytes for snes9x v12)."""
    out = bytearray(91)
    out[0] = 4       # SControlSnapshot.ver
    out[1] = 0x10    # Joypad[0].Buttons default idle mask
    out[7] = 0x10    # Joypad[1].Buttons default idle mask
    out[52] = 1      # mp5[0].pads[0] default
    out[63] = 1      # mp5[1].pads[0] default
    return bytes(out)
