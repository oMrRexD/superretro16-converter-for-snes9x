# Compatibility Notes

This converter targets SuperRetro16 save states and snes9x v12 save-state
streams in both directions. It is not a general save-state converter for every
SNES emulator.

## Supported Outputs

- snes9x slot save states (`.000` through `.999`).
- SuperRetro16 save states (`.s00` through `.s999`).
- `.srm` raw SRAM files.

## Supported Conversion Modes

- Standalone conversion from SR16 sections.
- Template conversion using a native snes9x reference state.
- Optional template register override.
- Optional template WRAM override.
- Reverse conversion from snes9x to SR16.
- Section dump mode for diagnostics.

## Areas Covered

The current implementation handles:

- CPU registers and scheduler migration.
- PPU layout remapping and first-frame runtime state.
- CGRAM/palette normalization and repair.
- DMA and selected first-frame DMA effects.
- FillRAM and selected hardware latch reconstruction.
- SPC/APU audio state and active voice continuation.
- SRAM extraction.
- Screenshot preview conversion.
- Several common optional chip-state chunks.

## Known Limits

- Save-state conversion is more fragile than SRAM extraction because it resumes
  mid-frame emulator internals.
- A reference snes9x template may be needed for difficult special-chip states.
- If a source save state lacks enough transient audio or chip state, the converter
  uses conservative reconstruction.
- PAL/NTSC and ROM-region mismatches can cause bad template results.
- The converter does not validate whether a ROM matches a save state. It only
  reads save-state files.

## Choosing a Mode

Use this order:

1. Standalone snes9x slot state.
2. Template snes9x slot state.
3. Template with `--template-reg` for special-chip hangs.
4. Template with `--template-ram` only as a last resort.
5. `.srm` extraction if save-state conversion remains unreliable.

## Reporting Compatibility Problems

A useful report includes:

- converter version or commit;
- Python version;
- exact command;
- `--dump` output;
- snes9x version;
- what happened after loading the converted state;
- whether `.srm` extraction worked.

Do not post ROMs, commercial save states, SRAM files, proprietary emulator
binaries, screenshots, or logs unless you have the right to share them.
