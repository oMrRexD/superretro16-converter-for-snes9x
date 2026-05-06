"""snes9x → SuperRetro16 conversion pipeline.

Orchestrates chunk extraction, state translation, and SR16 blob assembly.
"""
from __future__ import annotations
import gzip

from converter.common.format.snes9x import parse_snes9x
from converter.common.constants import SRAM_TARGET_SIZE, SR16_RM1_SIZE, SR16_SRAM_SIZE

from .format.sr16_writer import build_sr16_blob
from .state.cpu import build_c01
from .state.ppu import build_p01
from .state.palette import patch_p01_cgdata_as_rgb565
from .state.dma import build_d01
from .state.fillram import reconstruct_f01
from .state.audio import build_a01, build_ar1, build_ssz
from .state.chips import optional_sr16_chip_sections
from .state.screenshot import build_png_from_sho


def snes9x_to_sr16(input_path: str, output_path: str, *,
                    rom_path: str | None = None,
                    include_ssz: bool = True,
                    include_png: bool = True,
                    dump: bool = False) -> None:
    """Convert a snes9x v12 .000 save state to an SR16 .s0X file.

    Parameters
    ----------
    input_path : str
        Path to the snes9x .000 save state (gzipped or raw).
    output_path : str
        Path to write the SR16 .s0X file.
    rom_path : str | None
        Deprecated compatibility argument. Screenshots are built from the
        snes9x snapshot's SHO chunk; no ROM or emulator is used.
    include_ssz : bool
        If True, synthesize the SSZ (old SoundData) section.
    include_png : bool
        If True, synthesize the PNG (screenshot) section.
    dump : bool
        If True, print section info instead of writing.
    """
    with open(input_path, "rb") as f:
        blob = f.read()

    chunks = parse_snes9x(blob)

    if dump:
        print(f"snes9x save: {input_path}")
        print(f"Chunks found: {len(chunks)}")
        for name, data in chunks.items():
            print(f"  {name}: {len(data):>8d} bytes")
        return

    # --- Validate required chunks ---
    for required in ("CPU", "REG", "PPU", "DMA", "VRA", "RAM", "SRA", "FIL", "SND", "TIM"):
        if required not in chunks:
            raise ValueError(f"snes9x save missing required chunk: {required}")

    # --- Build SR16 sections ---
    sections: list[tuple[str, bytes]] = []

    # C01: CPU + REG + TIM
    c01 = build_c01(chunks["CPU"], chunks["REG"], chunks["TIM"])
    sections.append(("C01", c01))

    # P01: PPU, with CGRAM converted to SR16's RGB565 display cache.
    p01 = bytearray(build_p01(chunks["PPU"]))
    patch_p01_cgdata_as_rgb565(p01, chunks["PPU"])
    sections.append(("P01", bytes(p01)))

    sections.append(("D01", build_d01(chunks["DMA"])))

    # VR1: VRAM passthrough (64KB)
    sections.append(("VR1", chunks["VRA"]))

    # RM1: WRAM passthrough (128KB)
    ram = chunks["RAM"]
    if len(ram) > SR16_RM1_SIZE:
        ram = ram[:SR16_RM1_SIZE]
    elif len(ram) < SR16_RM1_SIZE:
        ram = ram + b"\x00" * (SR16_RM1_SIZE - len(ram))
    sections.append(("RM1", ram))

    # S01: SRAM (snes9x pads to 512KB, SR16 stores 128KB).
    sra = chunks["SRA"]
    if len(sra) > SR16_SRAM_SIZE:
        sra = sra[:SR16_SRAM_SIZE]
    elif len(sra) < SR16_SRAM_SIZE:
        sra = sra + b"\x00" * (SR16_SRAM_SIZE - len(sra))
    sections.append(("S01", sra))

    # F01: FillRAM with DMA registers reconstructed from DMA chunk
    f01 = reconstruct_f01(chunks["FIL"], chunks["DMA"])
    sections.append(("F01", f01))

    # A01: APU state (248B)
    sections.append(("A01", build_a01(chunks["SND"])))

    # AR1: SPC RAM (64KB)
    sections.append(("AR1", build_ar1(chunks["SND"])))

    # SSZ: old SoundData (1281B, optional)
    if include_ssz:
        sections.append(("SSZ", build_ssz(chunks["SND"])))

    # Chip sections
    chip_secs = optional_sr16_chip_sections(chunks)
    sections.extend(chip_secs)

    # PNG: screenshot (114688B, optional)
    if include_png:
        png = build_png_from_sho(chunks["SHO"]) if "SHO" in chunks else None
        if png is not None:
            sections.append(("PNG", png))

    # --- Assemble and write ---
    sr16_blob = build_sr16_blob(sections)

    with open(output_path, "wb") as f:
        f.write(sr16_blob)

    print(f"Converted: {input_path} -> {output_path}")
    print(f"  Sections: {len(sections)}")
    for code, data in sections:
        print(f"    {code}: {len(data):>8d} bytes")
    print(f"  Total size: {len(sr16_blob):,d} bytes")
