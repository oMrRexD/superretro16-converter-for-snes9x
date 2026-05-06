# Development Guide

This repository is intentionally small: it contains the public converter
package, tests, and documentation only.

## Package Layout

- `converter/common`: shared constants and SR16/snes9x container parsing.
- `converter/sr16_to_snes9x`: SR16 -> snes9x pipeline, state builders, audio,
  palette, DMA, and special-chip translators.
- `converter/snes9x_to_sr16`: snes9x -> SR16 pipeline and state builders.
- `converter/cli.py`: command-line interface.
- `tests/`: pure Python tests using synthetic binary data.

## Running Tests

```powershell
py -m pytest tests -q
```

The public test suite should not require ROMs, internal test data, emulator
binaries, Android tooling, or network access.

## Code Style

- Keep binary layouts explicit and well named.
- Prefer small helpers with focused tests.
- Avoid game-specific patches when a structural rule can explain the state.
- Keep public docs free of local paths, proprietary files, and internal logs.
- Do not add ROMs, save states, SRAM files, screenshots, audio dumps, APKs,
  DLLs, SO files, or generated debug artifacts to git.

## Adding Compatibility Fixes

When fixing a conversion issue:

1. Add or update a unit test with synthetic data when possible.
2. Keep the change in the smallest subsystem that owns the behavior.
3. Prefer format/state evidence over hard-coded game names.
4. Update public docs if the user-facing behavior changes.
5. Run the full test suite.

## Public Test Data Policy

Tests in this repository must be synthetic or legally redistributable. Do not
commit commercial save states, SRAM files, ROM-derived data, screenshots, PCM
captures, or binary emulator artifacts.

If a real-world issue requires non-public data to reproduce, keep that material
outside the public repository and reduce the fix to a synthetic unit test before
publishing.

## Release Workflow

The public repository has two GitHub Actions workflows:

- `.github/workflows/ci.yml` runs the Python test suite on pushes and pull
  requests to `main`.
- `.github/workflows/release.yml` runs tests, builds the Python package, creates
  a converter-only ZIP, uploads workflow artifacts, and creates a GitHub Release
  when a `v*` tag is pushed.

To publish a release:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

The release contains only the converter package and documentation artifacts. The
web app is deployed separately and is not bundled into GitHub Release downloads.
