"""Small visual comparison helper used by public tests.

This is the pure-data part of a larger visual debugging tool. It intentionally
does not render frames, load ROMs, or depend on emulator binaries.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from converter.common.constants import SR16_SCREEN_BYTES, SR16_SCREEN_HEIGHT, SR16_SCREEN_WIDTH

WIDTH = SR16_SCREEN_WIDTH
HEIGHT = SR16_SCREEN_HEIGHT


@dataclass
class VisualReport:
    valid: bool = False
    pixel_match_pct: float = 0.0
    color_distance_avg: float = 0.0
    color_distance_p95: float = 0.0
    worst_block_dist: float = 0.0
    high_dist_blocks: int = 0
    color_histogram_dist: float = 0.0
    palette_error: bool = False
    sprite_glitch: bool = False
    note: str = ""

    @property
    def has_issues(self) -> bool:
        return self.palette_error or self.sprite_glitch


def _decode_rgb565(data: bytes, le: bool = True) -> list[tuple[int, int, int]]:
    pixels = []
    order = "little" if le else "big"
    for i in range(0, len(data), 2):
        if i + 2 > len(data):
            break
        val = int.from_bytes(data[i:i + 2], order)
        red = (val >> 11) & 0x1F
        green = ((val >> 5) & 0x3F) >> 1
        blue = val & 0x1F
        pixels.append((red, green, blue))
    return pixels


def _histogram_color_distance(
    ref_pixels: list[tuple[int, int, int]],
    emu_pixels: list[tuple[int, int, int]],
    top_n: int = 128,
) -> float:
    ref_counts = Counter(ref_pixels)
    emu_counts = Counter(emu_pixels)
    if not ref_counts or not emu_counts:
        return 0.0

    def one_way(src: Counter, dst: Counter) -> float:
        dst_items = dst.most_common(top_n)
        total_cost = 0.0
        total_count = 0
        for (red, green, blue), count in src.most_common(top_n):
            best = min(
                (red - er) * (red - er)
                + (green - eg) * (green - eg)
                + (blue - eb) * (blue - eb)
                for (er, eg, eb), _dst_count in dst_items
            )
            total_cost += math.sqrt(best) * count
            total_count += count
        return total_cost / max(total_count, 1)

    return (one_way(ref_counts, emu_counts) + one_way(emu_counts, ref_counts)) / 2.0


def compare_visual(
    sr16_png: bytes,
    snes9x_fb: bytes,
    fb_width: int = WIDTH,
    fb_height: int = HEIGHT,
) -> VisualReport:
    report = VisualReport()
    if len(sr16_png) != SR16_SCREEN_BYTES:
        report.note = f"SR16 PNG wrong size ({len(sr16_png)} != {SR16_SCREEN_BYTES})"
        return report

    expected_fb_size = fb_width * fb_height * 2
    if len(snes9x_fb) < expected_fb_size:
        report.note = f"snes9x framebuffer too small ({len(snes9x_fb)} < {expected_fb_size})"
        return report

    report.valid = True
    ref_pixels = _decode_rgb565(sr16_png, le=True)
    emu_pixels = _decode_rgb565(snes9x_fb[:expected_fb_size], le=True)
    n = min(len(ref_pixels), len(emu_pixels), WIDTH * HEIGHT)
    report.color_histogram_dist = _histogram_color_distance(ref_pixels[:n], emu_pixels[:n])

    exact_matches = 0
    distances = []
    r_diff_total = 0
    g_diff_total = 0
    b_diff_total = 0
    for i in range(n):
        rr, rg, rb = ref_pixels[i]
        er, eg, eb = emu_pixels[i]
        if rr == er and rg == eg and rb == eb:
            exact_matches += 1
            distances.append(0.0)
            continue
        dr = rr - er
        dg = rg - eg
        db = rb - eb
        distances.append(math.sqrt(dr * dr + dg * dg + db * db))
        r_diff_total += abs(dr)
        g_diff_total += abs(dg)
        b_diff_total += abs(db)

    report.pixel_match_pct = exact_matches / n * 100 if n else 0.0
    report.color_distance_avg = sum(distances) / n if n else 0.0
    sorted_dists = sorted(distances)
    p95_idx = int(n * 0.95)
    report.color_distance_p95 = sorted_dists[p95_idx] if p95_idx < n else 0.0

    worst_block = 0.0
    high_dist_blocks = 0
    for by in range(HEIGHT // 8):
        for bx in range(WIDTH // 8):
            block_sum = 0.0
            for dy in range(8):
                for dx in range(8):
                    idx = (by * 8 + dy) * WIDTH + (bx * 8 + dx)
                    if idx < n:
                        block_sum += distances[idx]
            block_avg = block_sum / 64
            worst_block = max(worst_block, block_avg)
            if block_avg > 8.0:
                high_dist_blocks += 1
    report.worst_block_dist = worst_block
    report.high_dist_blocks = high_dist_blocks

    histogram_confirms_palette = report.color_histogram_dist > 0.5
    non_match = n - exact_matches
    total_channel_diff = r_diff_total + g_diff_total + b_diff_total
    if non_match > n * 0.005 and total_channel_diff > 0:
        max_ratio = max(r_diff_total, g_diff_total, b_diff_total) / total_channel_diff
        if histogram_confirms_palette and max_ratio > 0.55 and non_match > n * 0.01:
            report.palette_error = True
        if report.color_distance_avg > 6.0:
            report.palette_error = True
        if histogram_confirms_palette and worst_block > 12.0 and max_ratio > 0.45:
            report.palette_error = True

    same_palette_motion = (
        report.color_histogram_dist <= 0.5
        and report.color_distance_avg < 2.0
    )
    mild_same_palette_phase = (
        report.color_histogram_dist <= 0.5
        and report.color_distance_avg < 3.0
        and worst_block < 18.0
        and high_dist_blocks <= 32
    )
    widespread_same_palette = report.color_histogram_dist <= 0.5 and high_dist_blocks > 32
    if high_dist_blocks > 3 and not report.palette_error and not widespread_same_palette:
        if not same_palette_motion and not mild_same_palette_phase:
            report.sprite_glitch = True
    if (
        worst_block > 30.0
        and 4 <= high_dist_blocks <= 32
        and report.color_distance_avg < 4.0
        and not report.palette_error
    ):
        report.sprite_glitch = True
    if (
        worst_block > 15.0
        and report.color_distance_avg < 4.0
        and not report.palette_error
        and not widespread_same_palette
        and not same_palette_motion
        and not mild_same_palette_phase
    ):
        report.sprite_glitch = True

    return report
