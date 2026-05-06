"""Global compatibility defaults for state reconstruction.

This module deliberately avoids per-title profiles. It only contains evidence
sources that are safe to apply to every save. Optional special-chip chunks are
not emitted from here: snes9x 1.63 can crash after load when unrelated optional
chip chunks are present, so missing-chip stubs require structural evidence such
as the ROM header.
"""
from __future__ import annotations
from pathlib import Path
from urllib.parse import unquote

from converter.common.constants import SNES_CLK_SIZE, SNES_SRT_SIZE


# WRAM offsets (priority order) where games commonly keep a 512B CGRAM shadow.
# These are global evidence sources. Candidate palettes are still scored for
# plausibility and, when available, against the saved RGB565 framebuffer before
# being trusted.
GLOBAL_PALETTE_WRAM_OFFSETS: tuple[int, ...] = (0xC000, 0xC200, 0xC300, 0xC500)


_ROM_EXTS = (".sfc", ".smc", ".fig", ".swc")
_COPIER_HEADER_SIZE = 0x200
_HEADER_OFFSETS = (0x7FC0, 0xFFC0, 0x40FFC0)
_SRTC_CART_TYPES = {0x55}


def chip_stubs_for_source(source_name: str) -> tuple[tuple[str, int], ...]:
    """Return missing-chip stubs proven by a nearby ROM header.

    SR16 saves often do not serialize chips that are nevertheless mandatory for
    snes9x snapshot loading. We only emit these stubs when a ROM with the same
    stem can be found next to the save and its internal SNES header identifies
    the chip. This keeps normal saves free of unrelated optional chunks.
    """
    rom_path = _find_neighbor_rom(source_name)
    if rom_path is None:
        return ()
    header = _read_best_snes_header(rom_path)
    if header is None:
        return ()
    cart_type = header["cart_type"]
    if cart_type in _SRTC_CART_TYPES:
        return (("SRT", SNES_SRT_SIZE), ("CLK", SNES_CLK_SIZE))
    return ()


def _find_neighbor_rom(source_name: str) -> Path | None:
    if not source_name:
        return None
    source = Path(unquote(source_name))
    stems = [source.stem]
    decoded_stem = unquote(source.stem)
    if decoded_stem not in stems:
        stems.append(decoded_stem)

    for stem in stems:
        for ext in _ROM_EXTS:
            candidate = source.with_name(stem + ext)
            if candidate.is_file():
                return candidate
    return None


def _read_best_snes_header(rom_path: Path) -> dict[str, int | str] | None:
    try:
        data = rom_path.read_bytes()
    except OSError:
        return None

    candidates: list[tuple[int, dict[str, int | str]]] = []
    for base in (0, _COPIER_HEADER_SIZE):
        for off in _HEADER_OFFSETS:
            header_off = base + off
            if header_off + 0x40 > len(data):
                continue
            header = data[header_off:header_off + 0x40]
            score = _score_snes_header(header)
            if score > 0:
                candidates.append((score, {
                    "offset": header_off,
                    "title": header[:21].decode("ascii", "replace").rstrip(),
                    "map_mode": header[0x15],
                    "cart_type": header[0x16],
                }))

    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _score_snes_header(header: bytes) -> int:
    title = header[:21]
    printable = sum(0x20 <= b <= 0x7E for b in title)
    if printable < 12:
        return 0

    score = printable
    map_mode = header[0x15]
    if map_mode in {0x20, 0x21, 0x25, 0x30, 0x31, 0x32, 0x35, 0x3A}:
        score += 8

    checksum_complement = int.from_bytes(header[0x1C:0x1E], "little")
    checksum = int.from_bytes(header[0x1E:0x20], "little")
    if (checksum ^ checksum_complement) == 0xFFFF:
        score += 16

    return score
