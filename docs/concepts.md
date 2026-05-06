# Core Concepts

Save states are snapshots of an emulator's internal machine state. They are
not standardized across emulators. A converter has to translate both game
memory and emulator-specific runtime structures.

## SR16 Save State

An SR16 save contains a set of named binary sections. Important examples:

- CPU/register/timing data.
- PPU/video state.
- DMA state.
- WRAM, VRAM, SRAM, and hardware register mirrors.
- APU/SPC RAM and audio state.
- Optional special-chip sections.
- A preview framebuffer used by the source emulator UI.

The converter parses these sections with `converter.common.format.sr16`.

## snes9x Save State

snes9x stores a chunked snapshot. The converter writes a snes9x v12-compatible
stream with chunks such as:

- `CPU`, `REG`, and `TIM` for CPU scheduler/register/timing state.
- `PPU`, `DMA`, `FIL`, `VRA`, `RAM`, and `SRA` for graphics, hardware mirrors,
  and memory.
- `SND` for SPC/APU and DSP audio state.
- `CTL` for controller state.
- optional special-chip chunks such as SuperFX, SA-1, DSP, and Cx4 families.
- `SHO` for a snes9x-compatible screenshot preview when source preview data is
  available.

The snes9x container parser/writer lives in `converter.common.format.snes9x`.

## Why Conversion Is Hard

Several pieces of state are not laid out the same way in both emulators:

- PPU and DMA structures use different field orders.
- Some hardware registers are write-only and must be reconstructed from other
  evidence.
- Audio state includes hidden voice pipeline data, not just visible DSP
  registers.
- Special-chip games can depend on chip-internal transient buffers.
- First-frame correctness matters because the loaded state starts executing
  immediately.

This is why the converter does more than copy memory blocks.

## Standalone Mode vs Template Mode

Standalone mode reconstructs the snes9x state directly from the SR16 save.
It is the preferred mode when it works.

Template mode uses a native snes9x state for selected emulator-internal
structures. The SR16 memory regions still carry the user's game progress by
default. Template mode is a compatibility tool, especially for difficult
special-chip games.

## Battery Save Mode

Battery saves are different from save states. A `.srm` contains persistent
in-game save data, not the whole emulator machine state. This is much simpler
and often more reliable, but only preserves progress that the game wrote to
battery-backed SRAM.
