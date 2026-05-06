# File Format Overview

This page gives a high-level public overview of the file formats involved.
It is not a complete emulator-internal specification.

## SR16 Input

SR16 save states are binary files with multiple sections. The parser exposes
them as `SR16Save` and `SR16Section` objects:

- `SR16Save.sections`: ordered section list.
- `SR16Save.by_code(code)`: lookup by section code.
- `SR16Section.code`: section identifier.
- `SR16Section.size`: section size from the file.
- `SR16Section.data`: raw section payload.

The parser validates the save magic and decodes section markers before the
pipeline reads individual sections.

## snes9x Output

snes9x save states are written as a header followed by named chunks. Public
helpers:

- `parse_snes9x(blob)`: parse a snes9x snapshot into chunks.
- `write_chunk(name, data)`: encode one chunk.

The converter writes a v12-compatible chunk stream and gzip-compresses it for
normal snes9x slot-state output. The examples use `.000`, but snes9x also uses
other numeric slot extensions such as `.001`, `.002`, and up to `.999`.
snes9x EX+ uses the same snapshot bytes with a slot name like `.00.frz`,
`.01.frz`, or `.10.frz`; the browser app can emit or read that naming style
without changing the underlying state format.

## SRAM Output

`.srm` output is raw battery-backed SRAM. It has no snes9x save-state header.
The converter trims padded zero data to a common SRAM boundary while keeping a
minimum size suitable for typical games.

## Screenshot Preview

When the source save contains preview framebuffer data, the converter can emit
a snes9x screenshot chunk. This is only a menu/preview aid and is not used as
the authoritative game graphics state.

The browser app also uses embedded preview data for the result screen. SR16
`PNG` sections are raw 256x224 RGB565 framebuffers; snes9x and snes9x EX+
`SHO` chunks store an RGB screenshot buffer. Both are decoded locally in the
browser bridge and are never uploaded.
