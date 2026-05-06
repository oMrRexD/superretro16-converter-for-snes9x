# SaveShift Web

SaveShift is the browser UI for the SR16/snes9x save-state converter. It is a
static React/Vite app designed for Vercel. Conversion runs locally in the user's
browser through Pyodide inside a Web Worker; save states are not uploaded.

The app accepts SuperRetro16 save states (`.s00` through `.s999`), desktop
snes9x slot states (`.000` through `.999`), and snes9x EX+ slot states such as
`.00.frz`, `.01.frz`, and `.10.frz`. Users can drop one file or a batch of
files; batch conversion returns a local ZIP. Raw `.srm`/`.sav` files are not
accepted as inputs, but SRAM can still be extracted from SR16, snes9x, and
snes9x EX+ save states.

For single-file results, the UI shows the save's embedded screenshot when
present: SR16 `PNG` sections and snes9x/EX+ `SHO` chunks are decoded locally in
the Pyodide bridge.

## Development

```powershell
npm install
npm run dev
```

`npm run dev` and `npm run build` both generate `public/save-converter-python.pybundle`
from the repository's `converter/` and `web/python_bridge/` sources. The
snes9x -> SR16 reverse converter lives under `converter.snes9x_to_sr16`, so the
browser bundle no longer needs a second Python package for that direction.

## Build

```powershell
npm run build
npm run preview
```

Vercel settings:

- Build command: `cd web && npm ci && npm run build`
- Output directory: `web/dist`
- No serverless functions are required.

## Privacy and Legal Notes

The app processes files locally. It does not include ROMs, commercial save
states, SRAM files, emulator binaries, APKs, native libraries, or proprietary
assets.
