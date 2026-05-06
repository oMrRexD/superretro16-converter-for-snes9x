"""SaveShift bidirectional save-state converter package facade.

This module is a backward-compatible facade over the package modules.
External callers keep using `import converter as cv`. Nothing here adds
or removes behavior vs. the pre-refactor converter.py.

The package is organized around two conversion directions:
  common/           - shared constants and SR16/snes9x container helpers
  sr16_to_snes9x/   - SuperRetro16 to snes9x conversion
  snes9x_to_sr16/   - snes9x to SuperRetro16 conversion
"""
from __future__ import annotations

# ---- Constants ----------------------------------------------------------
from .common.constants import (
    SRAM_TARGET_SIZE,
    SR16_SCREEN_WIDTH, SR16_SCREEN_HEIGHT, SR16_SCREEN_BYTES,
    SHO_MAX_WIDTH, SHO_MAX_HEIGHT, SHO_DATA_BYTES,
)

# ---- format/ - SR16 codec + snes9x numeric-slot chunk container ---------
from .common.format.sr16 import (
    MARKER_KEYS, MARKER_LEN, decode_marker,
    SR16_MAGIC, SR16Section, SR16Save, parse_sr16,
)
from .common.format.snes9x import (
    SNES9X_VERSION, SNES9X_HEADER, write_chunk, parse_snes9x,
)

# ---- state/ - CPU/PPU/DMA/palette extraction ---------------------------
from .sr16_to_snes9x.state.cpu import (
    _extract_cpu, _prime_hdma_init_event,
    _cycles_until_next_irq, _sync_irq_timer_state,
)
from .sr16_to_snes9x.state.ppu import (
    _extract_ppu, _sync_ppu_postload_runtime,
)
from .sr16_to_snes9x.state.dma import (
    _extract_dma, _preexec_dmas,
)
from .sr16_to_snes9x.state.palette import (
    _wram_read, _decode_sr16_display_cgram, _repair_cgram_from_wram,
    _best_palette_by_screenshot, _write_cgram_from_values,
    _best_palette_candidate, _palette_values_be, _palette_values_le,
    _palette_values_rgb565_to_snes, _palette_stats,
    _plausible_palette, _palette_score, _palette_screenshot_score,
    _build_sho_from_sr16_png,
)

# ---- audio/ - Blargg voice resume + SND assembly -----------------------
from .sr16_to_snes9x.audio.brr import (
    _GAUSS_TABLE, _should_resume_ssz_voice, _s8,
    _quiet_duplicate_ssz_voice_mask, _zero_circular_region,
    _clear_initial_echo_buffer, _decode_brr_block,
    _next_brr_block_addr, _build_ssz_voice_window,
    _wrap_i16, _interp_gaussian, _predict_voice_output,
    _sample_ptr_distance, _calibrate_ssz_voice_window,
)
from .sr16_to_snes9x.audio.snd import (
    _extract_snd, _convert_old_spc_to_snd,
    _skip_old_spc_extra, _copy_old_spc_dsp_state, _default_ctl,
)

# ---- chips/ - SA1, SFX, DSP-1/2/4, Cx4 special-chip translators --------
from .sr16_to_snes9x.chips.state import (
    _reg_from_sr16_register_prefix, _build_sa1_chunks_from_sr16,
    _build_sfx_chunk_from_sax, _source_title,
    _dsp_chunk_name_for_sr16_psd, _dsp_payload_from_sr16_psd,
    _dp4_payload_from_sr16_psd, _default_dp4_chunk,
    _drain_dp4_chunk, _compatibility_stub_chip_chunks,
    _optional_chip_chunks_from_sr16,
)

# ---- Top-level pipeline + CLI ------------------------------------------
from .sr16_to_snes9x.pipeline import (
    extract_chunks_from_sr16, CHIP_CHUNK_NAMES, build_snes9x,
)
from .cli import main


__all__ = [
    # Constants
    "SRAM_TARGET_SIZE", "SR16_SCREEN_WIDTH", "SR16_SCREEN_HEIGHT",
    "SR16_SCREEN_BYTES", "SHO_MAX_WIDTH", "SHO_MAX_HEIGHT", "SHO_DATA_BYTES",
    # SR16 codec
    "MARKER_KEYS", "MARKER_LEN", "decode_marker",
    "SR16_MAGIC", "SR16Section", "SR16Save", "parse_sr16",
    # snes9x IO
    "SNES9X_VERSION", "SNES9X_HEADER", "write_chunk", "parse_snes9x",
    # CPU
    "_extract_cpu", "_prime_hdma_init_event",
    "_cycles_until_next_irq", "_sync_irq_timer_state",
    # PPU
    "_extract_ppu", "_sync_ppu_postload_runtime",
    # DMA
    "_extract_dma", "_preexec_dmas",
    # BRR
    "_GAUSS_TABLE", "_should_resume_ssz_voice", "_s8",
    "_quiet_duplicate_ssz_voice_mask", "_zero_circular_region",
    "_clear_initial_echo_buffer", "_decode_brr_block",
    "_next_brr_block_addr", "_build_ssz_voice_window",
    "_wrap_i16", "_interp_gaussian", "_predict_voice_output",
    "_sample_ptr_distance", "_calibrate_ssz_voice_window",
    # SND
    "_extract_snd", "_convert_old_spc_to_snd",
    "_skip_old_spc_extra", "_copy_old_spc_dsp_state", "_default_ctl",
    # Palette
    "_wram_read", "_decode_sr16_display_cgram", "_repair_cgram_from_wram",
    "_best_palette_by_screenshot", "_write_cgram_from_values",
    "_best_palette_candidate", "_palette_values_be", "_palette_values_le",
    "_palette_values_rgb565_to_snes", "_palette_stats",
    "_plausible_palette", "_palette_score", "_palette_screenshot_score",
    "_build_sho_from_sr16_png",
    # Chips
    "_reg_from_sr16_register_prefix", "_build_sa1_chunks_from_sr16",
    "_build_sfx_chunk_from_sax", "_source_title",
    "_dsp_chunk_name_for_sr16_psd", "_dsp_payload_from_sr16_psd",
    "_dp4_payload_from_sr16_psd", "_default_dp4_chunk",
    "_drain_dp4_chunk", "_compatibility_stub_chip_chunks",
    "_optional_chip_chunks_from_sr16",
    # Pipeline
    "extract_chunks_from_sr16", "CHIP_CHUNK_NAMES", "build_snes9x",
    # CLI
    "main",
]


if __name__ == "__main__":
    main()
