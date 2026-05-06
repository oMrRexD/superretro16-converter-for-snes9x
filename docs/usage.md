# Usage Guide

The converter reads SuperRetro16 save states (`.s00`, `.s01`, and similar) and
snes9x slot states (`.000`, `.001`, and similar). It can write:

- a snes9x save state (`.000`),
- a SuperRetro16 save state (`.s01`), or
- a raw SRAM file (`.srm`).

snes9x slot save states commonly use numeric extensions: `.000` for slot 0,
`.001` for slot 1, and so on. snes9x EX+ uses the same snapshot payload with
names such as `.00.frz`, `.01.frz`, and `.10.frz`. The examples below use
`.000`, but the same format applies to `.001` through `.999`.

In the browser app, choosing snes9x EX+ output changes only the filename style.
For example, slot `.000` becomes `.00.frz`, slot `.010` becomes `.10.frz`, and
slot `.100` becomes `.100.frz`.

Use only save states, SRAM files, and game files that you have the legal right
to use. This project does not include ROMs, commercial save states, SRAM files,
emulator binaries, APKs, or other copyrighted assets.

## Requirements

- Python 3.10 or newer.
- `pytest` only for running tests.

Install in editable mode for development:

```powershell
py -m pip install -e .[dev]
```

Or run directly from the repository:

```powershell
py -m converter --help
```

## Basic SR16 to snes9x Conversion

Standalone mode builds the snes9x state directly from the SR16 save:

```powershell
py -m converter sr16-to-snes9x "input.s01" "output.000"
```

Use this first for most games. It reconstructs CPU, PPU, DMA, audio, memory,
controller, timing, screenshot, and supported special-chip chunks from the SR16
state.

## Template Conversion

Template mode uses a native snes9x state as a source for emulator-internal
machine chunks, while preserving the SR16 game memory and default CPU register
position:

```powershell
py -m converter sr16-to-snes9x "input.s01" "output.000" --template "reference.000"
```

This can help with games whose state depends on emulator-internal details that
are difficult to reconstruct perfectly from the SR16 save alone.

The reference state should be from the same game and the same ROM region. It
does not need to represent the same in-game progress, but closer timing can
help with special-chip games.

## Template Register Override

Some special-chip games can be captured while the CPU is inside a chip
communication routine. In that case, the SR16 CPU register position may resume
poorly in snes9x even though memory is correct.

Use:

```powershell
py -m converter sr16-to-snes9x "input.s01" "output.000" --template "reference.000" --template-reg
```

Tradeoff: this can improve load stability, but it gives up the exact SR16 CPU
sub-frame execution point.

## Template WRAM Override

This is a last-resort option for special-chip games where in-flight WRAM
handshake state causes the converted state to hang or resume incorrectly:

```powershell
py -m converter sr16-to-snes9x "input.s01" "output.000" --template "reference.000" --template-ram
```

Tradeoff: this can lose the exact in-progress room/race/battle state because
WRAM comes from the template. Persistent progress may still be recoverable
through SRAM (`S01`) if the game uses battery-backed saves.

## snes9x to SR16 Conversion

Use the reverse subcommand to build a SuperRetro16 save state from a snes9x
slot state:

```powershell
py -m converter snes9x-to-sr16 "input.000" "output.s01"
```

The reverse converter uses the snes9x `SHO` screenshot chunk when present, so
it does not need a ROM or emulator just to generate the SR16 preview image.
Use `py -m converter snes9x-to-sr16`; the reverse direction is part of the
main `converter` package.

## Short Auto-Detect Commands

The CLI also accepts a shorter command shape that detects the input format:

```powershell
py -m converter "input.s01" "output.000"
py -m converter "input.s01" "output.srm" --srm
py -m converter "input.s01" --dump
```

The same form converts snes9x input back to SR16 when the output name is an
SR16 slot:

```powershell
py -m converter "input.000" "output.s08"
```

## Battery Save Extraction

If save-state conversion is not stable for a game, extracting SRAM is the
safest fallback:

```powershell
py -m converter extract-sram "input.s01" "output.srm"
```

Place the `.srm` next to the ROM using the filename expected by your snes9x
setup, then load the game normally and use the in-game load screen.

The browser app can also extract SRAM from snes9x and snes9x EX+ save states
when the snapshot contains a normal `SRA` chunk.

## Dump Mode

Dump mode lists the sections found inside an SR16 save:

```powershell
py -m converter dump "input.s01"
```

This is useful when reporting compatibility problems because it shows which
state sections are present and their sizes.

## Installed Console Script

If the package was installed with console scripts, use the generic entry point:

```powershell
saveshift sr16-to-snes9x "input.s01" "output.000"
saveshift snes9x-to-sr16 "input.000" "output.s01"
```

The dedicated `sr16-to-snes9x` console script is also available for SR16 →
snes9x conversion.

## Recommended Workflow

1. Try standalone snes9x slot-state conversion.
2. If the state loads but the game behaves incorrectly, try template mode.
3. For special-chip games, test `--template-reg` before `--template-ram`.
4. If state conversion remains unreliable, export `.srm` and load in-game.
5. When filing a bug, include the command used, the `--dump` output, and a
   description of what happens after loading. Do not attach ROMs or commercial
   save states or SRAM files publicly.
