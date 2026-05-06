"""Compatibility facade for SR16 APU sections -> snes9x SND helpers.

The production implementation is split by responsibility. Keep this module as
stable import surface for tests and older callers that import internal helper
names from ``converter.sr16_to_snes9x.audio.snd``.
"""
from __future__ import annotations

from .snd_assembly import _assemble_snd, _default_ctl
from .snd_binary import (
    _be_s16,
    _be_u,
    _pack_le_i16,
    _pack_le_i32,
    _pack_le_u16,
)
from .snd_dsp import (
    _DSP_POWERON_EXTERNAL_REGS,
    _build_dsp_state,
    _build_ipl_boot_dsp_state,
    _derive_noise_seed,
    _seed_voices_from_ssz,
    _u8_from_signed_high,
)
from .snd_old_spc import (
    _build_old_spc_safe_snd,
    _convert_old_spc_to_snd,
    _copy_old_spc_dsp_state,
    _old_spc_dsp_state_plausible,
    _seed_legacy_spc_visible_voices,
    _skip_old_spc_extra,
)
from .snd_pipeline import _extract_snd
from .snd_smp import (
    _build_smp_state,
    _looks_like_ipl_boot_snd,
    _smp_status_ram_byte,
    _smp_status_value,
    _swap_mailbox_ports,
    _sync_apu_mmio_shadow,
)

__all__ = [
    '_DSP_POWERON_EXTERNAL_REGS',
    '_be_u',
    '_be_s16',
    '_pack_le_i32',
    '_pack_le_u16',
    '_pack_le_i16',
    '_u8_from_signed_high',
    '_derive_noise_seed',
    '_swap_mailbox_ports',
    '_smp_status_ram_byte',
    '_smp_status_value',
    '_sync_apu_mmio_shadow',
    '_looks_like_ipl_boot_snd',
    '_build_smp_state',
    '_seed_voices_from_ssz',
    '_build_ipl_boot_dsp_state',
    '_build_dsp_state',
    '_assemble_snd',
    '_extract_snd',
    '_convert_old_spc_to_snd',
    '_build_old_spc_safe_snd',
    '_seed_legacy_spc_visible_voices',
    '_old_spc_dsp_state_plausible',
    '_skip_old_spc_extra',
    '_copy_old_spc_dsp_state',
    '_default_ctl',
]
