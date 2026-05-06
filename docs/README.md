# Documentation

This folder is the public documentation set for the SaveShift SR16/snes9x save
converter. It is written for users who want to convert their own saves in either
direction and for developers who want to understand the code without needing
internal research notes, ROMs, emulator binaries, or proprietary files.

## Start Here

- [Usage Guide](usage.md): install, command examples, and when to use each
  conversion mode.
- [Core Concepts](concepts.md): the save-state pieces the converter works with
  and why conversion is not a plain file rename.
- [Conversion Pipeline](conversion-pipeline.md): how SR16 sections are mapped
  into snes9x chunks.
- [File Format Overview](file-formats.md): high-level description of the input
  and output containers.
- [Compatibility Notes](compatibility.md): supported areas, known limits, and
  safer fallback strategies.
- [Troubleshooting](troubleshooting.md): common errors and practical fixes.
- [Development Guide](development.md): tests, package layout, and contribution
  expectations.
- [Public Release Policy](public-release-policy.md): what belongs in this
  public repository and what must stay out.

## What This Documentation Does Not Include

This public documentation intentionally avoids internal debug logs, ROM-specific
test data, extracted proprietary files, decompiled application assets, and
local machine paths. The converter can be used and tested from this repository
without those materials.
