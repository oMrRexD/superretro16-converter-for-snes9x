"""SR16 -> snes9x chunk assembly orchestration.

`extract_chunks_from_sr16` builds the standalone chunk dict directly from
an SR16 save (used when no `--template` is provided). `build_snes9x` writes
the final v12 freeze state stream, optionally fusing struct/chip chunks
from a reference template.
"""
from __future__ import annotations

from converter.common.constants import (
    SRAM_TARGET_SIZE,
    SR16_VR1_SIZE, SR16_RM1_SIZE, SR16_F01_SIZE,
    SNES_CPU_SIZE, SNES_REG_SIZE, SNES_TIM_SIZE,
    SNES_PPU_SIZE, SNES_DMA_SIZE,
)
from converter.common.format.sr16 import SR16Save
from converter.common.format.snes9x import SNES9X_HEADER, write_chunk
from .state.cpu import (
    _extract_cpu, _prime_hdma_init_event,
    _sync_frame_boundary_nmi_state, _sync_irq_timer_state,
)
from .state.ppu import _extract_ppu, _sync_ppu_postload_runtime
from .state.dma import _extract_dma, _preexec_dmas
from .state.fillram import _build_fillram_chunk
from .state.palette import (
    _decode_sr16_display_cgram,
    _repair_cgram_from_wram,
    _build_sho_from_sr16_png,
)
from .audio.snd_assembly import _default_ctl
from .audio.snd_pipeline import _extract_snd
from .chips.state import _optional_chip_chunks_from_sr16


# snes9x v12 chip-chunk names. Cross-checked against snapshot.cpp
# FreezeData[]: SFX, SA1, SAR, DP1, DP2, DP4, CX4, ST0, OBC, OBM, S71
# (SPC7110), SRT, CLK, BSX, MSU. DP3 and ST1/ST2 are NOT serialized by
# snes9x v12 — DP3 is intentionally omitted; ST011/ST018 have no chip
# chunk in this snes9x build.
#
# Coverage status:
#   * SFX/SA1/SAR/DP1/DP2/DP4/CX4/ST0/OBC/OBM/BSX/SRT/CLK — translated by
#     `chips/state.py` from SR16 sections (PSD, 4XC, SAX, register prefix)
#     or stubbed when SR16 omits them.
#   * S71 (SPC7110) — passthrough only via --template; SR16 does not
#     serialize SPC7110 transient state in a known section, so converted
#     standalone snapshots will not work for SPC7110 games (Far East of
#     Eden Zero, Tengai Makyou Zero) without a snes9x reference.
#   * MSU — passthrough only via --template; MSU-1 streaming state is not
#     part of SR16's saved data.
CHIP_CHUNK_NAMES = (
    "SFX", "SA1", "SAR", "DP1", "DP2", "DP4",
    "CX4", "ST0", "OBC", "OBM", "S71", "SRT", "CLK", "BSX", "MSU",
)


def extract_chunks_from_sr16(sr16: SR16Save,
                             vram_dma_mode: str = "off") -> dict[str, bytes]:
    """Build snes9x-compatible chunk dict directly from SR16 data.

    ``vram_dma_mode`` is forwarded to ``_preexec_dmas`` (see ``state.dma``).
    Default is ``"off"`` which preserves the byte-equal behavior validated
    against the calibration set.
    """
    c01 = sr16.by_code("C01")
    p01 = sr16.by_code("P01")
    d01 = sr16.by_code("D01")
    f01 = sr16.by_code("F01")
    rm1 = sr16.by_code("RM1")
    vr1 = sr16.by_code("VR1")
    png = sr16.by_code("PNG")
    chip_chunks = dict(_optional_chip_chunks_from_sr16(sr16))

    chunks: dict[str, bytes] = {}
    chunks["NAM"] = b"Converted\x00"
    if c01:
        cpu, reg, tim = _extract_cpu(c01.data)
        cpu, tim = _sync_frame_boundary_nmi_state(cpu, tim, f01.data if f01 else None)
        cpu = _prime_hdma_init_event(cpu, f01.data if f01 else None)
        chunks["CPU"] = cpu
        chunks["REG"] = reg
        chunks["TIM"] = tim
    else:
        chunks["CPU"] = b"\x00" * SNES_CPU_SIZE
        chunks["REG"] = b"\x00" * SNES_REG_SIZE
        chunks["TIM"] = b"\x00" * SNES_TIM_SIZE

    ppu_bytes = bytearray(_extract_ppu(p01.data) if p01 else b"\x00" * SNES_PPU_SIZE)
    _decode_sr16_display_cgram(ppu_bytes, png.data if png else None)
    if rm1:
        _repair_cgram_from_wram(
            ppu_bytes,
            rm1.data,
            f01.data if f01 else None,
            png.data if png else None,
        )
    if f01 and rm1 and p01:
        _preexec_dmas(
            ppu_bytes, rm1.data, f01.data,
            vram=bytearray(vr1.data) if vr1 else None,
            vram_dma_mode=vram_dma_mode,
        )
    cpu, tim, synced_ppu = _sync_irq_timer_state(
        chunks["CPU"], chunks["TIM"], bytes(ppu_bytes), f01.data if f01 else None
    )
    chunks["CPU"] = cpu
    chunks["TIM"] = tim
    chunks["PPU"] = _sync_ppu_postload_runtime(
        synced_ppu, f01.data if f01 else None, chunks["CPU"]
    )

    chunks["DMA"] = (
        _extract_dma(d01.data, f01.data if f01 else None)
        if d01 else b"\x00" * SNES_DMA_SIZE
    )
    chunks["SND"] = _extract_snd(sr16)
    chunks["CTL"] = _default_ctl()
    for name, data in chip_chunks.items():
        chunks[name] = data
    if f01:
        chunks["FIL"] = _build_fillram_chunk(
            f01.data,
            set(chip_chunks),
            chunks["PPU"],
            vr1.data if vr1 else None,
            chunks["CPU"],
            chunks["TIM"],
            chunks["SND"],
        )
    sho = _build_sho_from_sr16_png(png.data if png else None)
    if sho is not None:
        chunks["SHO"] = sho
    return chunks


REQUIRED_TEMPLATE_CHUNKS = ("CPU", "REG", "PPU", "DMA", "SND", "CTL", "TIM")


def _validate_template_chunks(template_chunks: dict[str, bytes],
                              use_template_ram: bool) -> None:
    """Reject template dicts missing chunks we will index unconditionally."""
    missing = [n for n in REQUIRED_TEMPLATE_CHUNKS if n not in template_chunks]
    if missing:
        raise ValueError(
            f"snes9x template missing required chunk(s): {', '.join(missing)}"
        )
    if use_template_ram and "RAM" not in template_chunks:
        raise ValueError(
            "--template-ram requested but template has no RAM chunk"
        )


def _validate_sr16_for_build(vra, ram, sra, fil) -> None:
    """Replace bare assertions with explicit, named ValueErrors."""
    if vra is None:
        raise ValueError("SR16 missing VR1 (VRAM) section")
    if len(vra.data) != SR16_VR1_SIZE:
        raise ValueError(
            f"SR16 VR1 size {len(vra.data)} != expected {SR16_VR1_SIZE}"
        )
    if ram is None:
        raise ValueError("SR16 missing RM1 (WRAM) section")
    if len(ram.data) != SR16_RM1_SIZE:
        raise ValueError(
            f"SR16 RM1 size {len(ram.data)} != expected {SR16_RM1_SIZE}"
        )
    if sra is None:
        raise ValueError("SR16 missing S01 (SRAM) section")
    if len(sra.data) > SRAM_TARGET_SIZE:
        raise ValueError(
            f"SR16 S01 (SRAM) size {len(sra.data)} exceeds snes9x target "
            f"{SRAM_TARGET_SIZE} — game cart uses larger SRAM than supported"
        )
    if fil is None:
        raise ValueError("SR16 missing F01 (FillRAM) section")
    if len(fil.data) != SR16_F01_SIZE:
        raise ValueError(
            f"SR16 F01 size {len(fil.data)} != expected {SR16_F01_SIZE}"
        )
    # SR16 always serializes 128KB of SRAM. Larger carts (Star Fox 2 hacks,
    # 256KB homebrews) would lose data when round-tripped through this
    # converter; warn so the user notices. Most games are <= 32KB so this
    # almost never fires.
    if len(sra.data) > 0x20000:
        import warnings
        warnings.warn(
            f"SR16 SRAM section is {len(sra.data)} bytes — > 128KB indicates "
            "an unusual cart; verify the converted .000 preserves all SRAM",
            stacklevel=3,
        )


def build_snes9x(sr16: SR16Save, template_chunks: dict[str, bytes],
                 use_template_reg: bool = False,
                 use_template_ram: bool = False) -> bytes:
    """Build a snes9x v12 stream.

    Struct chunks (CPU/REG/PPU/DMA/SND/CTL/TIM/NAM) come from template_chunks
    (which may be extracted from SR16 via extract_chunks_from_sr16). Memory
    regions always come from SR16 so CPU registers, stack, and game state stay
    consistent.

    Chip chunks (DP4/CX4/SFX/SA1/SAR/...) prefer the template when present —
    SR16's serialized chip state is often missing transient buffers needed to
    resume mid-chip-routine. SR16 chip chunks are used only as fallback.

    use_template_reg: if True, REG comes from the template instead of SR16.
    Loses SR16's execution point (PC/SP) but avoids freezes when SR16 captured
    mid-chip-routine (Top Gear 3000 / DSP-4).

    use_template_ram: if True, WRAM also comes from the template. Last-resort
    flag for chip games where SR16's WRAM holds in-flight chip-communication
    state that breaks resume even with clean machine state. Loses SR16's
    in-progress run state; SR16 SRA still preserves persistent progress.
    """
    _validate_template_chunks(template_chunks, use_template_ram)
    c01 = sr16.by_code("C01")
    if c01:
        _, sr16_reg, _ = _extract_cpu(c01.data)
    else:
        sr16_reg = None

    out = bytearray()
    out += SNES9X_HEADER
    out += write_chunk("NAM", template_chunks.get("NAM", b"Removed\x00"))
    for name in ("CPU", "REG", "PPU", "DMA"):
        if name == "REG" and sr16_reg is not None and not use_template_reg:
            data = sr16_reg
        else:
            data = template_chunks[name]
        out += write_chunk(name, data)

    vra = sr16.by_code("VR1")
    ram = sr16.by_code("RM1")
    sra = sr16.by_code("S01")
    fil = sr16.by_code("F01")
    _validate_sr16_for_build(vra, ram, sra, fil)
    out += write_chunk("VRA", vra.data)
    if use_template_ram:
        # Validated above to be present when use_template_ram is True.
        out += write_chunk("RAM", template_chunks["RAM"])
    else:
        out += write_chunk("RAM", ram.data)
    out += write_chunk("SRA", sra.data + b"\x00" * (SRAM_TARGET_SIZE - len(sra.data)))
    sr16_chip_chunks = dict(_optional_chip_chunks_from_sr16(sr16))
    vr1 = sr16.by_code("VR1")
    out += write_chunk(
        "FIL",
        _build_fillram_chunk(
            fil.data,
            set(sr16_chip_chunks),
            template_chunks.get("PPU"),
            vr1.data if vr1 else None,
            template_chunks.get("CPU"),
            template_chunks.get("TIM"),
            template_chunks.get("SND"),
        )
    )

    out += write_chunk("SND", template_chunks["SND"])
    out += write_chunk("CTL", template_chunks["CTL"])
    out += write_chunk("TIM", template_chunks["TIM"])

    for name in CHIP_CHUNK_NAMES:
        if name in template_chunks:
            out += write_chunk(name, template_chunks[name])
            sr16_chip_chunks.pop(name, None)
    for name, data in sr16_chip_chunks.items():
        out += write_chunk(name, data)

    png = sr16.by_code("PNG")
    sho = _build_sho_from_sr16_png(png.data if png else None)
    if sho is None:
        sho = template_chunks.get("SHO")
    if sho is not None:
        out += write_chunk("SHO", sho)
    return bytes(out)
