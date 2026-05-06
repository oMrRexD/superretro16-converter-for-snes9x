"""SR16 P01 -> snes9x v12 PPU chunk field remapper.

The two emulators serialize PPU fields in different orders. This module
builds the snes9x PPU chunk by walking the snes9x SnapPPU layout in order,
looking up each field by name in the SR16 FreezeData table, and copying
bytes from P01 at SR16's serialization offset to the snes9x output offset.

Build the snes9x layout statically from snapshot.cpp (SnapPPU[]) plus
ppu.h (SPPU struct) field sizes. Total = 2652 bytes (v12).
"""
from __future__ import annotations
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# -- snes9x v12 SnapPPU layout in order, with sizes from SPPU struct -----
def _build_snes9x_layout():
    """Return list of (name, size_bytes) in snes9x serialization order.
    Total must be 2652 bytes."""
    L: list[tuple[str, int]] = []
    L += [
        ("VMA.High", 1),
        ("VMA.Increment", 1),
        ("VMA.Address", 2),
        ("VMA.Mask1", 2),
        ("VMA.FullGraphicCount", 2),
        ("VMA.Shift", 2),
        ("WRAM", 4),
    ]
    for n in range(4):
        L += [
            (f"BG[{n}].SCBase", 2),
            (f"BG[{n}].HOffset", 2),
            (f"BG[{n}].VOffset", 2),
            (f"BG[{n}].BGSize", 1),
            (f"BG[{n}].NameBase", 2),
            (f"BG[{n}].SCSize", 2),
        ]
    L += [
        ("BGMode", 1),
        ("BG3Priority", 1),
        ("CGFLIP", 1),
        ("CGFLIPRead", 1),
        ("CGADD", 1),
        ("CGSavedByte", 1),         # v11
        ("CGDATA", 256 * 2),        # 512 bytes (uint16[256])
    ]
    for n in range(128):
        L += [
            (f"OBJ[{n}].HPos", 2),       # int16
            (f"OBJ[{n}].VPos", 2),
            (f"OBJ[{n}].HFlip", 1),
            (f"OBJ[{n}].VFlip", 1),
            (f"OBJ[{n}].Name", 2),
            (f"OBJ[{n}].Priority", 1),
            (f"OBJ[{n}].Palette", 1),
            (f"OBJ[{n}].Size", 1),
        ]
    L += [
        ("OBJThroughMain", 1),
        ("OBJThroughSub", 1),
        ("OBJAddition", 1),
        ("OBJNameBase", 2),
        ("OBJNameSelect", 2),
        ("OBJSizeSelect", 1),
        ("OAMAddr", 2),
        ("SavedOAMAddr", 2),
        ("OAMPriorityRotation", 1),
        ("OAMFlip", 1),
        ("OAMReadFlip", 1),
        ("OAMTileAddress", 2),
        ("OAMWriteRegister", 2),
        ("OAMData", 544),
        ("FirstSprite", 1),
        ("LastSprite", 1),
        ("HTimerEnabled", 1),
        ("VTimerEnabled", 1),
        ("HTimerPosition", 2),       # short
        ("VTimerPosition", 2),
        ("IRQHBeamPos", 2),
        ("IRQVBeamPos", 2),
        ("HBeamFlip", 1),
        ("VBeamFlip", 1),
        ("HBeamPosLatched", 2),
        ("VBeamPosLatched", 2),
        ("GunHLatch", 2),            # missing in SR16
        ("GunVLatch", 2),            # missing in SR16
        ("HVBeamCounterLatched", 1),
        ("Mode7HFlip", 1),
        ("Mode7VFlip", 1),
        ("Mode7Repeat", 1),
        ("MatrixA", 2), ("MatrixB", 2), ("MatrixC", 2), ("MatrixD", 2),
        ("CentreX", 2), ("CentreY", 2),
        ("M7HOFS", 2), ("M7VOFS", 2),
        ("Mosaic", 1), ("MosaicStart", 1),
        ("BGMosaic", 4),             # bool8[4]
        ("Window1Left", 1), ("Window1Right", 1),
        ("Window2Left", 1), ("Window2Right", 1),
        ("RecomputeClipWindows", 1),
    ]
    for n in range(6):
        L += [
            (f"ClipCounts[{n}]", 1),
            (f"ClipWindowOverlapLogic[{n}]", 1),
            (f"ClipWindow1Enable[{n}]", 1),
            (f"ClipWindow2Enable[{n}]", 1),
            (f"ClipWindow1Inside[{n}]", 1),    # SR16 calls this Outside
            (f"ClipWindow2Inside[{n}]", 1),
        ]
    L += [
        ("ForcedBlanking", 1),
        ("FixedColourRed", 1),
        ("FixedColourGreen", 1),
        ("FixedColourBlue", 1),
        ("Brightness", 1),           # SR16 has 2B Brightness; take low byte
        ("ScreenHeight", 2),
        ("Need16x8Mulitply", 1),
        ("BGnxOFSbyte", 1),
        ("M7byte", 1),
        ("HDMA", 1),                 # missing in SR16
        ("HDMAEnded", 1),            # missing in SR16
        ("OpenBus1", 1),
        ("OpenBus2", 1),
        ("VRAMReadBuffer", 2),       # v11, missing in SR16
    ]
    return L


SNES9X_LAYOUT = _build_snes9x_layout()
_total = sum(sz for _, sz in SNES9X_LAYOUT)
assert _total == 2652, f"snes9x PPU layout sum is {_total}, expected 2652"


# -- name normalization ---------------------------------------------------
# SR16 uses VMA_X with underscore; snes9x uses VMA.X with dot.
# SR16 calls ClipWindow*Outside what snes9x calls ClipWindow*Inside.
def sr16_name(snes9x_name: str) -> str:
    n = snes9x_name
    if n.startswith("VMA."):
        n = "VMA_" + n[4:]
    n = n.replace("ClipWindow1Inside", "ClipWindow1Outside")
    n = n.replace("ClipWindow2Inside", "ClipWindow2Outside")
    return n


# -- main remapper --------------------------------------------------------
def remap_p01_to_ppu(p01: bytes, verbose: bool = False) -> tuple[bytes, list[str]]:
    """Build snes9x v12 PPU chunk (2652B) from SR16 P01 (2645B).

    Returns (output_bytes, missing_field_names).
    """
    if len(p01) != 2645:
        raise ValueError(f"P01 size mismatch: {len(p01)} != 2645")

    # Load SR16 layout. Path is resolved relative to this file so it works
    # regardless of the user's cwd or how the package is installed.
    table_path = os.path.join(os.path.dirname(__file__), "freezedata.json")
    with open(table_path) as f:
        d = json.load(f)
    sr16_index: dict[str, dict] = {e["name"]: e for e in d["p01"]}

    out = bytearray(2652)
    cur = 0
    missing: list[str] = []

    for s9x_name, s9x_size in SNES9X_LAYOUT:
        sr_name = sr16_name(s9x_name)
        e = sr16_index.get(sr_name)
        if e is None:
            missing.append(s9x_name)
            cur += s9x_size  # leave zeros
            continue

        sr_off = e["serial_off"]
        sr_size = e["serial_size"]

        if sr_size == s9x_size:
            out[cur:cur + s9x_size] = p01[sr_off:sr_off + sr_size]
        elif sr_size > s9x_size:
            # SR16 has wider field. Take last s9x_size bytes (low bytes, BE).
            # E.g. Brightness: SR16 2B BE -> snes9x 1B.
            out[cur:cur + s9x_size] = p01[sr_off + sr_size - s9x_size:sr_off + sr_size]
        else:
            # SR16 narrower than snes9x: zero-pad MSB (BE).
            out[cur + s9x_size - sr_size:cur + s9x_size] = p01[sr_off:sr_off + sr_size]

        if verbose:
            print(f"  s9x[{cur:5d}..+{s9x_size}]  <- sr16[{sr_off:5d}..+{sr_size}]  {s9x_name}")
        cur += s9x_size

    assert cur == 2652

    # --- Post-remap corrections ---
    # 1. Brightness: SR16 uses scale 1-16, snes9x uses 0-15.
    # 2. ClipWindow Inside/Outside semantics inversion.
    off = 0
    for name, sz in SNES9X_LAYOUT:
        if name == "Brightness":
            out[off] = max(0, min(15, out[off] - 1))
        if "ClipWindow1Inside" in name or "ClipWindow2Inside" in name:
            out[off] = 1 if out[off] == 0 else 0
        off += sz

    return bytes(out), missing


if __name__ == "__main__":
    import sys, gzip
    sr16_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "Super Metroid.s01")
    with open(sr16_path, "rb") as f:
        blob = f.read()
    # Find P01 the easy way: import converter
    import sys as _sys
    _sys.path.insert(0, ROOT)
    import converter as cv
    sr16 = cv.parse_sr16(blob)
    p01 = sr16.by_code("P01").data
    ppu, missing = remap_p01_to_ppu(p01)
    print(f"Remapped {len(p01)} -> {len(ppu)} bytes")
    print(f"Missing fields ({len(missing)}): {missing}")
