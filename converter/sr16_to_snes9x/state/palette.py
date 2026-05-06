"""WRAM/CGRAM palette recovery + SHO screenshot embedding.

CGRAM palette recovery uses three independent evidence sources:
1. Known WRAM shadow addresses (game-specific fixed offsets)
2. Armed CGRAM DMA source (when an upload was queued at save time)
3. Saved framebuffer (RGB565 colors must approximate the picked palette)

SHO embedding lifts SR16's 256x224 RGB565 framebuffer into snes9x's
SHO chunk format (512x478 max RGB888 buffer).
"""
from __future__ import annotations

from converter.common.constants import (
    SR16_SCREEN_BYTES, SR16_SCREEN_WIDTH, SR16_SCREEN_HEIGHT,
    SHO_DATA_BYTES,
    PPU_OFF_CGDATA, CGRAM_BYTES, CGRAM_ENTRIES,
    MDMAEN, DMA_REGS_BASE, DMA_REGS_END, DMA_CH_STRIDE,
    DMA_OFF_BBAD, DMA_OFF_A1TL, DMA_OFF_A1TH, DMA_OFF_A1B,
    DMA_OFF_DASL, DMA_OFF_DASH,
    BBUS_CGDATA,
    WRAM_BANK_LOW, WRAM_BANK_HIGH, WRAM_LOW_HALF_BYTES,
)
from ..game_registry import GLOBAL_PALETTE_WRAM_OFFSETS


# --- Empirical palette thresholds. ---
# These constants used to be magic numbers scattered through
# `_repair_cgram_from_wram` and `_decode_sr16_display_cgram`. Each was tuned
# empirically against the calibration save set; widening any one of them
# without re-running the internal regression harness typically breaks at
# least one save. They are kept here so the names document intent and
# future tuning lives in one place.

# A serialized P01 CGDATA is treated as "bad enough to repair from WRAM"
# when at least this many entries have bit-15 set OR the palette is heavily
# dominated by one channel (see CURRENT_BAD_* constants).
CURRENT_BAD_HIGH_BIT_COUNT = 8
CURRENT_BAD_NONZERO_THRESHOLD = 64
CURRENT_BAD_UNIQUE_THRESHOLD = 16
CURRENT_BAD_DOMINANCE = 0.78

# When a PNG screenshot is provided and the trusted candidate's
# screenshot-distance is much worse than the RGB565-converted current
# CGDATA, prefer RGB565. Compared as (rgb565 * NUM) < (trusted * DEN).
RGB565_OVER_TRUSTED_NUM = 4
RGB565_OVER_TRUSTED_DEN = 3

# When choosing between masked-current and RGB565-converted-current with
# a PNG screenshot, prefer RGB565 when it scores at least ~10% better.
RGB565_OVER_MASKED_NUM = 10
RGB565_OVER_MASKED_DEN = 9

# A direct (no-shadow) candidate is only worth a fallback aligned scan
# of WRAM if its screenshot score exceeds this threshold (high score =
# poor match), indicating the candidate is suspect.
DIRECT_SCAN_FALLBACK_SCORE = 100_000

# Aligned scan stride for the WRAM fallback search. 32 bytes is broad
# enough to cover real palette shadows but skips the slow byte-by-byte
# search the original two-byte sliding scan used.
ALIGNED_SCAN_STRIDE = 0x20

# Aligned scan accepts a candidate only if it scores at least ~10% better
# than the direct rgb565/masked candidate.
ALIGNED_OVER_DIRECT_NUM = 10
ALIGNED_OVER_DIRECT_DEN = 9

# A "plausible" palette must have no high-bit-15 entries, at least this
# many non-zero colors, this many unique colors, and stay below the
# dominance/dark0 ceilings.
PLAUSIBLE_MIN_NONZERO = 64
PLAUSIBLE_MIN_UNIQUE = 32
PLAUSIBLE_MAX_DOMINANCE = 0.72
PLAUSIBLE_MAX_DARK0 = 48

# Best screenshot-match thresholds for `_best_palette_by_screenshot`.
SCREENSHOT_PERFECT_SCORE = 0
SCREENSHOT_STRONG_MATCH_LIMIT = 25_000

# Trusted candidate priority bonuses fed into _palette_score for ranking.
TRUSTED_KNOWN_SHADOW_PRIORITY = 1000
TRUSTED_DMA_SOURCE_PRIORITY = 2000

# Display-color-cache ratio for `_decode_sr16_display_cgram`: prefer
# RGB565 conversion when its screenshot score is at least ~10% better
# than the raw CGDATA score, OR when the raw CGDATA still has high bits
# set and the RGB565 score is strictly better.
DISPLAY_RGB565_BETTER_NUM = 10
DISPLAY_RGB565_BETTER_DEN = 9
DISPLAY_RGB565_NONZERO_RATIO = 0.75


def _wram_read(wram: bytes, src_long: int, count: int) -> bytes:
    """Read up to `count` bytes from WRAM at SNES address `src_long` (24-bit).
    Returns empty bytes if address is outside WRAM (e.g. ROM)."""
    bank = (src_long >> 16) & 0xFF
    offs = src_long & 0xFFFF
    if bank == WRAM_BANK_LOW:
        wram_off = offs
    elif bank == WRAM_BANK_HIGH:
        wram_off = WRAM_LOW_HALF_BYTES + offs
    elif bank < 0x40 and offs < 0x2000:
        # Banks $00-$3F mirror WRAM low 8KB at $0000-$1FFF
        wram_off = offs
    elif 0x80 <= bank <= 0xBF and offs < 0x2000:
        wram_off = offs
    else:
        return b""
    if wram_off >= len(wram):
        return b""
    return wram[wram_off:wram_off + count]


def _repair_cgram_from_wram(ppu: bytearray, wram: bytes,
                            f01: bytes | None = None,
                            png: bytes | None = None) -> bool:
    """Replace bad SR16 CGDATA with a plausible palette shadow from WRAM.

    SR16's P01 CGDATA can contain stale/invalid values with bit 15 set. That
    works poorly in snes9x, and some games (ALTTP) do not have an armed CGRAM
    DMA at the save point to overwrite it on load. Several games keep a 512B
    little-endian CGRAM shadow in WRAM; copy it into the big-endian snapshot
    CGDATA field when the serialized PPU palette is clearly invalid or strongly
    color-biased in the classic "first frame all blue/green" way.
    """
    if len(ppu) < PPU_OFF_CGDATA + CGRAM_BYTES or len(wram) < WRAM_LOW_HALF_BYTES:
        return False

    cgram_off = PPU_OFF_CGDATA
    current = _palette_values_be(ppu[cgram_off:cgram_off + CGRAM_BYTES])
    current_stats = _palette_stats(current)
    current_bad = (
        current_stats["high_bits"] >= CURRENT_BAD_HIGH_BIT_COUNT
        or (
            current_stats["nonzero"] >= CURRENT_BAD_NONZERO_THRESHOLD
            and current_stats["unique"] >= CURRENT_BAD_UNIQUE_THRESHOLD
            and current_stats["dominance"] >= CURRENT_BAD_DOMINANCE
        )
    )

    trusted_candidates: list[tuple[int, int]] = []
    seen: set[int] = set()

    def add_candidate(off: int, priority: int = 0) -> None:
        if off < 0 or off + CGRAM_BYTES > len(wram) or off in seen:
            return
        seen.add(off)
        trusted_candidates.append((priority, off))

    # Known shadows found so far. Keep these first so existing gold saves stay
    # stable before trying any lower-confidence candidate. The list lives in
    # converter.sr16_to_snes9x.game_registry so per-game knobs are centralized.
    for off in GLOBAL_PALETTE_WRAM_OFFSETS:
        add_candidate(off, TRUSTED_KNOWN_SHADOW_PRIORITY)

    # If a game has prepared a CGRAM DMA but SR16 captured before it fired,
    # the DMA source is usually the most trustworthy palette shadow.
    if f01 is not None and len(f01) >= DMA_REGS_END:
        dma_enable = f01[MDMAEN]
        for ch in range(8):
            ri = DMA_REGS_BASE + ch * DMA_CH_STRIDE
            if not (dma_enable & (1 << ch)) or f01[ri + DMA_OFF_BBAD] != BBUS_CGDATA:
                continue
            src = (f01[ri + DMA_OFF_A1TL]
                   | (f01[ri + DMA_OFF_A1TH] << 8)
                   | (f01[ri + DMA_OFF_A1B] << 16))
            count = f01[ri + DMA_OFF_DASL] | (f01[ri + DMA_OFF_DASH] << 8)
            if count == 0:
                count = 0x10000
            if count >= CGRAM_BYTES:
                data = _wram_read(wram, src, CGRAM_BYTES)
                if len(data) == CGRAM_BYTES:
                    bank = (src >> 16) & 0xFF
                    off = (src & 0xFFFF) + (
                        WRAM_LOW_HALF_BYTES if bank == WRAM_BANK_HIGH else 0
                    )
                    add_candidate(off, TRUSTED_DMA_SOURCE_PRIORITY)

    masked_current = [v & 0x7FFF for v in current]
    rgb565_current = _palette_values_rgb565_to_snes(current)
    partial_rgb565_current = [
        rgb565_current[i] if current[i] & 0x8000 else masked_current[i]
        for i in range(CGRAM_ENTRIES)
    ]
    masked_stats = _palette_stats(masked_current)
    rgb565_stats = _palette_stats(rgb565_current)
    partial_rgb565_stats = _palette_stats(partial_rgb565_current)
    if png is not None:
        screenshot_candidates = [
            (masked_current, masked_stats),
            (partial_rgb565_current, partial_rgb565_stats),
            (rgb565_current, rgb565_stats),
        ]
        for _priority, off in trusted_candidates:
            vals = _palette_values_le(wram[off:off + CGRAM_BYTES])
            stats = _palette_stats(vals)
            if _plausible_palette(stats):
                screenshot_candidates.append((vals, stats))
        best_values = _best_palette_by_screenshot(screenshot_candidates, png)
        if best_values is not None:
            _write_cgram_from_values(ppu, best_values, cgram_off)
            return True
    if not current_bad:
        return False

    best = _best_palette_candidate(wram, trusted_candidates)
    if best is not None:
        _score, off = best
        trusted_values = _palette_values_le(wram[off:off + CGRAM_BYTES])
        if png is not None and current_stats["high_bits"]:
            trusted_score = _palette_screenshot_score(trusted_values, png)
            rgb565_score = _palette_screenshot_score(rgb565_current, png)
            if (
                trusted_score is not None
                and rgb565_score is not None
                and _plausible_palette(rgb565_stats)
                and rgb565_score * RGB565_OVER_TRUSTED_NUM
                    < trusted_score * RGB565_OVER_TRUSTED_DEN
            ):
                _write_cgram_from_values(ppu, rgb565_current, cgram_off)
                return True

        _write_cgram_from_values(ppu, trusted_values, cgram_off)
        return True

    if current_stats["high_bits"]:
        use_rgb565 = False
        if png is not None:
            masked_score = _palette_screenshot_score(masked_current, png)
            rgb565_score = _palette_screenshot_score(rgb565_current, png)
            if rgb565_score is not None and (
                masked_score is None
                or rgb565_score * RGB565_OVER_MASKED_NUM
                    < masked_score * RGB565_OVER_MASKED_DEN
                or not _plausible_palette(masked_stats)
            ):
                use_rgb565 = True

            direct_stats = rgb565_stats if use_rgb565 else masked_stats
            direct_score = rgb565_score if use_rgb565 else masked_score
            if (
                direct_score is not None
                and direct_score > DIRECT_SCAN_FALLBACK_SCORE
                and _plausible_palette(direct_stats)
            ):
                # Some saves keep a clean WRAM CGRAM shadow outside the known
                # fixed addresses. Scan on palette-sized alignment only: it is
                # broad enough for real shadows but avoids the old slow sliding
                # two-byte search on common RGB565 cases.
                aligned_candidates = (
                    (0, off) for off in range(
                        0, len(wram) - (CGRAM_BYTES - 1), ALIGNED_SCAN_STRIDE
                    )
                )
                aligned_best = _best_palette_candidate(wram, aligned_candidates)
                if aligned_best is not None:
                    _score, aligned_off = aligned_best
                    aligned_values = _palette_values_le(
                        wram[aligned_off:aligned_off + CGRAM_BYTES]
                    )
                    aligned_score = _palette_screenshot_score(aligned_values, png)
                    if (
                        aligned_score is not None
                        and aligned_score * ALIGNED_OVER_DIRECT_NUM
                            < direct_score * ALIGNED_OVER_DIRECT_DEN
                    ):
                        _write_cgram_from_values(ppu, aligned_values, cgram_off)
                        return True
        elif _plausible_palette(rgb565_stats):
            use_rgb565 = True

        if use_rgb565 and (
            _plausible_palette(rgb565_stats)
            or not _plausible_palette(masked_stats)
            or png is not None
        ):
            _write_cgram_from_values(ppu, rgb565_current, cgram_off)
            return True

        if _plausible_palette(masked_stats):
            _write_cgram_from_values(ppu, masked_current, cgram_off)
            return True

    return False


def _decode_sr16_display_cgram(ppu: bytearray, png: bytes | None = None) -> bool:
    """Convert SR16's serialized display-color CGRAM into raw snes9x CGRAM.

    SR16's P01 ``CGDATA`` is usually not the raw SNES BGR555 CGRAM that snes9x
    snapshots expect. It is the emulator's RGB565 display palette cache. The
    old WRAM repair path hid that for many games; this normalizes the primary
    PPU extraction so the palette is sane even when no WRAM-shadow repair is
    needed or enabled.
    """
    if len(ppu) < PPU_OFF_CGDATA + CGRAM_BYTES:
        return False

    current = _palette_values_be(
        ppu[PPU_OFF_CGDATA:PPU_OFF_CGDATA + CGRAM_BYTES]
    )
    current_stats = _palette_stats(current)
    rgb565_current = _palette_values_rgb565_to_snes(current)
    rgb565_stats = _palette_stats(rgb565_current)

    should_convert = False
    if png is not None:
        current_score = _palette_screenshot_score(
            [value & 0x7FFF for value in current], png
        )
        rgb565_score = _palette_screenshot_score(rgb565_current, png)
        if rgb565_score is not None and current_score is not None:
            should_convert = (
                rgb565_score == 0
                or rgb565_score * DISPLAY_RGB565_BETTER_NUM
                    < current_score * DISPLAY_RGB565_BETTER_DEN
                or (current_stats["high_bits"] and rgb565_score < current_score)
            )
    else:
        should_convert = (
            current_stats["high_bits"] > 0
            and rgb565_stats["high_bits"] == 0
            and rgb565_stats["nonzero"]
                >= current_stats["nonzero"] * DISPLAY_RGB565_NONZERO_RATIO
        )

    if not should_convert:
        return False

    _write_cgram_from_values(ppu, rgb565_current, PPU_OFF_CGDATA)
    return True


def _best_palette_by_screenshot(
    candidates: list[tuple[list[int], dict[str, float]]],
    png: bytes,
) -> list[int] | None:
    """Pick a CGRAM candidate proven by SR16's embedded framebuffer.

    Some SR16 saves serialize PPU.CGDATA as display RGB565 instead of raw SNES
    BGR555. Others keep a WRAM shadow that looks statistically plausible but is
    not the palette used by the saved frame. The framebuffer is the strongest
    local evidence we have, so let a very strong screenshot match override the
    older generic plausibility filters.
    """
    scored: list[tuple[int, list[int], dict[str, float]]] = []
    for values, stats in candidates:
        if stats["high_bits"] != 0 or stats["nonzero"] < 32 or stats["unique"] < 16:
            continue
        score = _palette_screenshot_score(values, png)
        if score is None:
            continue
        scored.append((score, values, stats))
    if not scored:
        return None

    scored.sort(key=lambda item: (item[0], -_palette_score(item[2])))
    best_score, best_values, best_stats = scored[0]
    if best_score == SCREENSHOT_PERFECT_SCORE:
        return best_values
    if best_score <= SCREENSHOT_STRONG_MATCH_LIMIT and _plausible_palette(best_stats):
        return best_values
    return None


def _write_cgram_from_values(ppu: bytearray, values: list[int],
                             cgram_off: int = PPU_OFF_CGDATA) -> None:
    for i, value in enumerate(values[:CGRAM_ENTRIES]):
        ppu[cgram_off + i * 2:cgram_off + i * 2 + 2] = (value & 0x7FFF).to_bytes(2, "big")


def _best_palette_candidate(wram: bytes, candidates) -> tuple[float, int] | None:
    best: tuple[float, int] | None = None
    for priority, off in candidates:
        vals = _palette_values_le(wram[off:off + CGRAM_BYTES])
        stats = _palette_stats(vals)
        if not _plausible_palette(stats):
            continue
        score = _palette_score(stats) + priority
        if best is None or score > best[0]:
            best = (score, off)
    return best


def _palette_values_be(data: bytes) -> list[int]:
    return [int.from_bytes(data[i:i + 2], "big") for i in range(0, CGRAM_BYTES, 2)]


def _palette_values_le(data: bytes) -> list[int]:
    return [int.from_bytes(data[i:i + 2], "little") for i in range(0, CGRAM_BYTES, 2)]


def _palette_values_rgb565_to_snes(values: list[int]) -> list[int]:
    """Convert SR16 display-color CGDATA (RGB565) to snes9x raw CGRAM."""
    out: list[int] = []
    for value in values:
        red = (value >> 11) & 0x1F
        green = (value >> 6) & 0x1F
        blue = value & 0x1F
        out.append(red | (green << 5) | (blue << 10))
    return out


def _palette_stats(values: list[int]) -> dict[str, float]:
    visible = [v & 0x7FFF for v in values]
    r_total = sum(v & 0x1F for v in visible)
    g_total = sum((v >> 5) & 0x1F for v in visible)
    b_total = sum((v >> 10) & 0x1F for v in visible)
    total = r_total + g_total + b_total
    return {
        "high_bits": sum(1 for v in values if v & 0x8000),
        "nonzero": sum(1 for v in visible if v != 0),
        "unique": len(set(visible)),
        "dominance": (max(r_total, g_total, b_total) / total) if total else 0.0,
        "dark0": ((visible[0] & 0x1F)
                  + ((visible[0] >> 5) & 0x1F)
                  + ((visible[0] >> 10) & 0x1F)),
    }


def _plausible_palette(stats: dict[str, float]) -> bool:
    return (
        stats["high_bits"] == 0
        and stats["nonzero"] >= PLAUSIBLE_MIN_NONZERO
        and stats["unique"] >= PLAUSIBLE_MIN_UNIQUE
        and stats["dominance"] <= PLAUSIBLE_MAX_DOMINANCE
        and stats["dark0"] <= PLAUSIBLE_MAX_DARK0
    )


def _palette_score(stats: dict[str, float]) -> float:
    return (
        stats["unique"] * 4
        + stats["nonzero"]
        - stats["dominance"] * 120
        - stats["dark0"] * 0.25
    )


def _palette_screenshot_score(values: list[int], png: bytes) -> int | None:
    """Score a CGRAM candidate against SR16's embedded RGB565 framebuffer.

    The SR16 "PNG" chunk is actually a 256x224 16-bit framebuffer. Besides
    becoming the optional SHO snapshot image, it is useful for deciding whether
    P01.CGDATA is raw SNES color or already-converted RGB565 display color.
    """
    if len(png) != SR16_SCREEN_BYTES:
        return None

    counts: dict[tuple[int, int, int], int] = {}
    for i in range(0, len(png), 2):
        value = int.from_bytes(png[i:i + 2], "little")
        color = ((value >> 11) & 0x1F, (value >> 6) & 0x1F, value & 0x1F)
        if sum(color) <= 3:
            continue
        counts[color] = counts.get(color, 0) + 1

    samples = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:96]
    if not samples:
        return None

    palette = [
        (value & 0x1F, (value >> 5) & 0x1F, (value >> 10) & 0x1F)
        for value in values
    ]
    total = 0
    for color, count in samples:
        red, green, blue = color
        best = min(
            (red - pr) * (red - pr)
            + (green - pg) * (green - pg)
            + (blue - pb) * (blue - pb)
            for pr, pg, pb in palette
        )
        total += best * count
    return total


def _build_sho_from_sr16_png(png: bytes | None) -> bytes | None:
    """Build snes9x's SHO screenshot chunk from SR16's RGB565 framebuffer."""
    if png is None or len(png) != SR16_SCREEN_BYTES:
        return None

    out = bytearray()
    out += SR16_SCREEN_WIDTH.to_bytes(2, "big")
    out += SR16_SCREEN_HEIGHT.to_bytes(2, "big")
    out.append(0)  # Interlaced

    data = bytearray(SHO_DATA_BYTES)
    src = 0
    dst = 0
    for _y in range(SR16_SCREEN_HEIGHT):
        for _x in range(SR16_SCREEN_WIDTH):
            value = int.from_bytes(png[src:src + 2], "little")
            src += 2
            data[dst] = (value >> 11) & 0x1F
            data[dst + 1] = (value >> 6) & 0x1F
            data[dst + 2] = value & 0x1F
            dst += 3

    out += data
    return bytes(out)
