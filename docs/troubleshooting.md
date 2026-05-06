# Troubleshooting

## `output is required when not --dump`

You ran a conversion command without an output path.

Correct:

```powershell
py -m converter "input.s01" "output.000"
```

For inspection only:

```powershell
py -m converter "input.s01" --dump
```

## `no S01 (SRAM) section found in SR16 save`

The save does not contain a battery-backed SRAM section. The game may not use
SRAM, or the source save may not include that section.

Try snes9x slot-state conversion instead of `--srm`.

## Converted State Does Not Load in snes9x

Try these steps:

1. Confirm the output uses the numeric slot extension expected by your snes9x
   setup, such as `.000`, `.001`, or another slot number.
2. Confirm the ROM region/version matches the save.
3. Try template mode with a native snes9x state from the same game.
4. For special-chip games, try `--template-reg`.
5. If the game still fails, extract `.srm` and use the in-game load screen.

## Game Loads But Graphics Are Wrong

Possible causes:

- ROM/version mismatch.
- Template state from the wrong ROM or region.
- A game-specific first-frame PPU/DMA pattern not yet covered.

Try standalone conversion first. If using a template, create a fresh reference
state from the same ROM and region.

## Game Loads But Audio Clicks or Instruments Are Wrong

Audio save-state conversion depends on hidden DSP voice state. The converter
reconstructs and phase-aligns active voices, but some states may still expose
edge cases.

Try:

1. Standalone conversion.
2. Template conversion.
3. SRAM extraction if exact audio continuation is less important than progress.

When reporting an audio issue, describe whether the problem happens only in the
first frame/second or persists after gameplay continues.

## Special-Chip Game Hangs

Some special-chip games depend on transient chip communication buffers.

Try:

```powershell
py -m converter "input.s01" "output.000" --template "reference.000" --template-reg
```

If that still fails:

```powershell
py -m converter "input.s01" "output.000" --template "reference.000" --template-ram
```

Use `--template-ram` carefully because it may lose the exact in-progress game
state.

## Tests Fail After Local Edits

Run:

```powershell
py -m pytest tests -q
```

If only visual comparison tests fail, check `tests/visual_compare_helper.py`.
If audio tests fail, check the BRR/phase/SND modules under
`converter/sr16_to_snes9x/audio`.
