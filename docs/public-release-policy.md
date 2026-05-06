# Public Release Policy

The public repository should contain the converter, the web UI, tests, and
documentation only.

## Keep Out

- ROMs, ROM-derived assets, commercial save states, and SRAM files.
- Emulator binaries, APKs, native libraries, patched binaries, and decompiled
  third-party app files.
- Internal debug logs, local filesystem paths, screenshots, PCM/WAV captures,
  temporary sweep outputs, and machine-specific configuration.

## Before Publishing

Run the Python tests, build the web app, and check `git status --short`.
Tracked files should be source code, docs, tests, package metadata, web source
assets, and license/ignore files only.
