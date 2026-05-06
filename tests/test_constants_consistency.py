"""Tests that verify cross-module invariants between constants and behavior.

These catch the kind of off-by-one regression that would silently slip past
modular tests but break byte-equal output.
"""
from __future__ import annotations

from converter.common import constants as C


def test_snd_internal_layout_is_contiguous():
    """SND blocks must butt up against each other with no gap or overlap."""
    assert C.SND_OFF_SPC_RAM == 0
    assert C.SND_OFF_SMP == C.SND_OFF_SPC_RAM + 65536
    assert C.SND_OFF_DSP == C.SND_OFF_SMP + C.SND_SMP_BYTES
    assert C.SND_OFF_TAIL == C.SND_OFF_DSP + C.SND_DSP_BYTES
    # Tail + padding fills out to the chunk size
    assert C.SND_OFF_TAIL + C.SND_TAIL_BYTES <= C.SNES_SND_SIZE


def test_smp_block_size_matches_field_count():
    assert C.SND_SMP_BYTES == C.SND_SMP_FIELDS * 4


def test_dma_register_block_spans_8_channels():
    assert C.DMA_REGS_END == C.DMA_REGS_BASE + 8 * C.DMA_CH_STRIDE


def test_dsp_voice_block_size():
    """8 voices * 38B = 304B, ending exactly at echo_hist."""
    assert C.DSP_OFF_VOICES + 8 * C.DSP_VOICE_STRIDE == C.DSP_OFF_ECHO_HIST


def test_dsp_external_regs_at_misc_plus_49():
    """DSP misc fields are 49B, then external_regs (mirror of regs)."""
    assert C.DSP_OFF_EXTERNAL_REGS == C.DSP_OFF_MISC + 49


def test_dsp_misc_field_relative_offsets():
    """Spot-check a few named misc offsets land where SPC_DSP::copy_state expects."""
    assert C.DSP_MISC_NEW_KON  == 475
    assert C.DSP_MISC_ENDX_BUF == 476
    assert C.DSP_MISC_T_DIR    == 482
    assert C.DSP_MISC_T_ESA    == 490


def test_voice_block_stride_matches_layout():
    """Per-voice fields must fit within DSP_VOICE_STRIDE bytes."""
    last_byte = C.VOICE_OFF_T_ENVX_OUT
    assert last_byte < C.DSP_VOICE_STRIDE


def test_chunk_sizes_are_positive():
    """Sanity: all declared sizes are non-zero."""
    sizes = [
        C.SR16_C01_SIZE, C.SR16_P01_SIZE, C.SR16_D01_SIZE,
        C.SR16_VR1_SIZE, C.SR16_RM1_SIZE, C.SR16_F01_SIZE,
        C.SR16_A01_SIZE, C.SR16_AR1_SIZE, C.SR16_SSZ_SIZE,
        C.SR16_PSD_SIZE, C.SR16_4XC_SIZE,
        C.SNES_CPU_SIZE, C.SNES_REG_SIZE, C.SNES_TIM_SIZE,
        C.SNES_PPU_SIZE, C.SNES_DMA_SIZE, C.SNES_SND_SIZE,
        C.SNES_DP4_SIZE, C.SNES_SFX_SIZE, C.SNES_SA1_SIZE,
        C.SNES_SAR_SIZE, C.SNES_BSX_SIZE, C.SNES_SRT_SIZE,
        C.SNES_CLK_SIZE, C.SNES_OBC_SIZE, C.SNES_OBM_SIZE,
        C.SNES_ST0_SIZE,
    ]
    assert all(s > 0 for s in sizes)


def test_sho_total_size_matches_screen_geometry():
    assert C.SR16_SCREEN_BYTES == C.SR16_SCREEN_WIDTH * C.SR16_SCREEN_HEIGHT * 2
    assert C.SHO_DATA_BYTES == C.SHO_MAX_WIDTH * C.SHO_MAX_HEIGHT * 3


def test_clip_block_fits_in_ppu_chunk():
    """Six 6-byte clip slots must fit between PPU_OFF_CLIP_BLOCK and the
    fixed-color fields that follow."""
    end_of_clip_block = (
        C.PPU_OFF_CLIP_BLOCK + 6 * C.PPU_CLIP_SLOT_STRIDE
    )
    assert end_of_clip_block <= C.PPU_OFF_FIXED_COLOR_R


def test_ppu_irq_field_offsets_strictly_increase():
    """The IRQ-timer fields are a contiguous block we write together."""
    seq = [
        C.PPU_OFF_HTIMER_ENABLED, C.PPU_OFF_VTIMER_ENABLED,
        C.PPU_OFF_HTIMER_POS, C.PPU_OFF_VTIMER_POS,
        C.PPU_OFF_IRQ_H_BEAM, C.PPU_OFF_IRQ_V_BEAM,
    ]
    assert seq == sorted(seq)


def test_chip_chunk_names_includes_all_sr16_supported_chips():
    """Pipeline iterates CHIP_CHUNK_NAMES to fuse template chip chunks. Any
    optional chunk emitted by chip_state must be representable here."""
    from converter.sr16_to_snes9x.pipeline import CHIP_CHUNK_NAMES
    expected = {"SFX", "SA1", "SAR", "DP1", "DP2", "DP4",
                "CX4", "ST0", "OBC", "OBM", "BSX", "SRT", "CLK"}
    assert expected.issubset(set(CHIP_CHUNK_NAMES))


def test_facade_reexports_all_named_symbols():
    """Every name in __all__ resolves on the package facade."""
    import converter as cv
    missing = [n for n in cv.__all__ if not hasattr(cv, n)]
    assert missing == []
