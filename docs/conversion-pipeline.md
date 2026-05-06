# Conversion Pipeline

The public entry point is `converter.cli:main`. The two conversion directions
are separate internally: SR16 -> snes9x lives in
`converter.sr16_to_snes9x.pipeline`, while snes9x -> SR16 lives in
`converter.snes9x_to_sr16.pipeline`.

## High-Level Flow

1. Parse the SR16 save container.
2. Either build a standalone template from SR16 sections or load a snes9x
   reference template.
3. Build a snes9x v12 chunk stream.
4. Gzip the final stream with deterministic gzip metadata.

## Standalone Chunk Construction

Standalone conversion builds a chunk dictionary from the SR16 state:

- CPU/register/timing chunks are extracted from the SR16 CPU section and then
  normalized for snes9x scheduler expectations.
- PPU data is remapped into snes9x layout.
- CGRAM/palette data is normalized and repaired from reliable sources when the
  source emulator stored display-cache colors instead of raw SNES colors.
- DMA state is rebuilt from SR16 DMA data and hardware register mirrors.
- Some already-armed DMA effects are pre-applied to avoid first-frame graphics
  artifacts.
- FillRAM is rebuilt from the source hardware mirror plus reconstructed latch
  values.
- Audio is assembled from SPC RAM, APU CPU state, DSP registers, and old audio
  voice-state data when available.
- Special-chip chunks are synthesized or translated for supported chips.
- A screenshot chunk is generated from source preview framebuffer data when
  possible.

## Final snes9x Stream

`build_snes9x` writes chunks in the order expected by snes9x:

- metadata and core machine chunks;
- memory chunks (`VRA`, `RAM`, `SRA`, `FIL`);
- audio, controller, and timing chunks;
- optional special-chip chunks;
- optional screenshot chunk.

In normal mode, memory comes from SR16 so the user's game state stays intact.
In template mode, selected machine chunks can come from the reference snes9x
state to improve compatibility.

## Reverse Pipeline

The reverse converter reads a snes9x v12 snapshot and builds SR16 sections:

- CPU, register, and timing chunks become `C01`.
- PPU, VRAM, WRAM, FillRAM, DMA, and SRAM become the matching SR16 state
  sections.
- snes9x `SND` is translated into SR16 audio sections (`A01`, `AR1`, and
  optional `SSZ`).
- snes9x `SHO` is converted into SR16's raw RGB565 `PNG` preview section.
- Supported optional chip chunks are mapped back into SR16 chip sections when
  enough state is present.

Code that needs the reverse direction should import from
`converter.snes9x_to_sr16`.

## Audio Pipeline

The SR16 -> snes9x audio implementation is split across
`converter.sr16_to_snes9x.audio`:

- `snd_pipeline.py` orchestrates SR16 audio sections into snes9x `SND`.
- `snd_smp.py` rebuilds the SPC700/SMP CPU block.
- `snd_dsp.py` rebuilds DSP state and seeds active voices.
- `snd_old_spc.py` handles older combined SPC snapshots.
- `brr_decode.py`, `phase_*`, and `voice_policy.py` handle BRR window
  reconstruction and first-frame voice continuation.

The goal is to avoid restarting active notes from the beginning of their
samples while also preventing first-frame clicks caused by stale hidden audio
history.

## Video and Palette Pipeline

The video path maps SR16 PPU data into snes9x's PPU chunk, then fixes runtime
state needed immediately after load. Palette recovery uses multiple signals:

- source PPU color data;
- source preview framebuffer color plausibility;
- WRAM palette shadows;
- armed CGRAM DMA data when available.

The result should render with correct colors from the first snes9x frame for
known tested games.

## Special-Chip Pipeline

The converter has public translators for known optional chip chunks. These are
best-effort translations designed to produce snes9x-compatible chunk shapes
without shipping any external emulator binaries.

When a chip's transient internal state is not fully represented in the SR16
save, template mode can be safer than standalone mode.
