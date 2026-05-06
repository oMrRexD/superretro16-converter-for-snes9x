
# SaveShift: SuperRetro16 (formerly SuperGNES) and Snes9X Save State Converter

Use it online: https://saveshift.vercel.app

Convert save states between SuperRetro16 (`.s00`, `.s01`, etc.) and snes9x-compatible slot save states (`.000`, `.001`, etc.), or extract raw SRAM files (`.srm`).

## Why this exists

For years, I played a lot of Super Nintendo games on an old phone using SuperRetro16. Much later, I found that phone again and discovered thousands of old SuperRetro16 save states still on it.

I wanted to revisit those saves on my PC, but SuperRetro16 save states were only compatible with SuperRetro16 itself. They could not be loaded directly in snes9x or other common SNES emulators.

The usual workaround would have been slow: open each state in SuperRetro16, load the game, save normally in-game, extract SRAM, and repeat. I built SaveShift to avoid doing that manually.

This project was developed through AI-assisted development with Claude Opus 4.7
and GPT-5.5, with real save states tested over many rounds of conversion,
emulator comparison, audio debugging, visual debugging, and special-chip
compatibility work.

## What it does

SaveShift can:

- Convert SuperRetro16 save states to snes9x slot save states.
- Convert snes9x slot save states back to SuperRetro16 save states.
- Extract raw SRAM files (`.srm`) from SR16 or snes9x states.
- Convert snes9x slot states to snes9x EX+ filename style in the web app.
- Inspect save-state sections/chunks for debugging.

## Status

- SR16 -> snes9x standalone conversion: working for the current validation set.
- SR16 -> snes9x template conversion: available for games that need a native snes9x reference state.
- snes9x -> SR16 conversion: available through the unified CLI and web app.
- SRAM extraction: working.
- Web app: available through the Vercel link above once deployed.

The converter has been tested with many real save states from different games,
including Chrono Trigger, Super Metroid, Mega Man X, Mega Man X3, The Legend of
Zelda: A Link to the Past, Super Bomberman 5, Donkey Kong Country, Final
Fantasy V, Top Gear 3000, and others.

## Requirements

- Python 3.10 or newer.
- `pytest` only if you want to run the test suite.

Install for development:

```powershell
py -m pip install -e .[dev]
```

Run directly from the repository:

```powershell
py -m converter --help
```

## Usage

Convert a SuperRetro16 save state to a standalone snes9x state:

```powershell
py -m converter sr16-to-snes9x "input.s01" "output.000"
```

Convert using a native snes9x reference state as a template:

```powershell
py -m converter sr16-to-snes9x "input.s01" "output.000" --template "reference.000"
```


Convert a snes9x slot state back to SuperRetro16:

```powershell
py -m converter snes9x-to-sr16 "input.000" "output.s01"
```

Extract a raw SRAM file:

```powershell
py -m converter extract-sram "input.s01" "output.srm"
```

Inspect a save state:

```powershell
py -m converter dump "input.s01"
py -m converter dump "input.000"
```

The shorter auto-detect form is also supported:

```powershell
py -m converter "input.s01" "output.000"
py -m converter "input.s01" "output.srm" --srm
```

It also auto-detects snes9x input and converts back to SR16 when the output
name is an SR16 slot:

```powershell
py -m converter "input.000" "output.s08"
```

If installed with console scripts, you can also use:

```powershell
saveshift sr16-to-snes9x "input.s01" "output.000"
saveshift snes9x-to-sr16 "input.000" "output.s01"
sr16-to-snes9x "input.s01" "output.000"
```

## Package layout

The main package keeps the two conversion directions separate:

- `converter/common/`: shared constants and SR16/snes9x container helpers.
- `converter/sr16_to_snes9x/`: SuperRetro16 to snes9x conversion.
- `converter/snes9x_to_sr16/`: snes9x to SuperRetro16 conversion.
- `converter/cli.py`: unified command-line interface.

## Tests

```powershell
py -m pytest tests -q
```

The tests use synthetic binary data. They do not require ROMs, emulator binaries, save states, or SRAM files.

## Documentation

Detailed public documentation lives in [`docs/`](docs/README.md):

- [Usage Guide](docs/usage.md)
- [Core Concepts](docs/concepts.md)
- [Conversion Pipeline](docs/conversion-pipeline.md)
- [File Format Overview](docs/file-formats.md)
- [Compatibility Notes](docs/compatibility.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Development Guide](docs/development.md)
- [Public Release Policy](docs/public-release-policy.md)

## Legal notes

This project is not affiliated with Neutron Emulation, the Snes9X Team,
Nintendo, or any game publisher.

This repository does not include ROMs, SRAM files,
SuperRetro16 binaries, snes9x binaries, APKs, or proprietary game assets.

SaveShift is an independently implemented converter that reads and writes
compatible save-state formats. SuperRetro16 and Snes9X are separate projects
with their own licenses and distribution terms.

## Contributing

The project is open to pull requests. If you find a bug or a game that does not convert correctly, please open an issue with the command used, the emulator/version, and a description of what happened. Do not attach ROMs, or proprietary game assets publicly.

You can also contact me on Discord: `.2by.`

## License

MIT. See `LICENSE`.
