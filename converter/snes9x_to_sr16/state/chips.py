"""snes9x chip chunks → SR16 chip sections (SAX, SA1, PSD, 4XC)."""
from __future__ import annotations

from converter.common.constants import (
    SR16_SAX_SIZE, SR16_SA1_SIZE, SR16_PSD_SIZE, SR16_4XC_SIZE,
    SNES_SFX_SIZE, SNES_SAR_SIZE, SNES_DP4_SIZE,
    SR16_REG_OFF_DB, SR16_REG_OFF_P, SR16_REG_OFF_A, SR16_REG_OFF_D,
    SR16_REG_OFF_S, SR16_REG_OFF_X, SR16_REG_OFF_Y, SR16_REG_OFF_PC_FULL,
)


_SFX_REG_COUNT = 16
_SFX_TAIL_OFF = _SFX_REG_COUNT * 4
_SFX_STATUS_REL = 8
_SFX_COLOR_REL = 0
_SFX_COLOR_WORD_INDEX = 26
_DP1_PAYLOAD_SIZE = 1449
_DP4_DATA_BASE = 0x14
_DSP4_BUFFER_SIZE = 1024


def build_sax_from_sfx(sfx: bytes) -> bytes | None:
    """Compact snes9x SFX(996B) back to SR16 SAX(71B)."""
    if len(sfx) < SNES_SFX_SIZE:
        return None
    out = bytearray(SR16_SAX_SIZE)
    # First 16 avReg values: snes9x stores as 32-bit BE, SR16 as 16-bit BE pairs
    for i in range(_SFX_REG_COUNT):
        val = int.from_bytes(sfx[i * 4:i * 4 + 4], "big") & 0xFFFF
        out[i * 2:i * 2 + 2] = val.to_bytes(2, "big")
    # Remaining 19 words from tail fields (best-effort mapping)
    status = int.from_bytes(
        sfx[_SFX_TAIL_OFF + _SFX_STATUS_REL:_SFX_TAIL_OFF + _SFX_STATUS_REL + 4],
        "big",
    ) & 0xFFFF
    out[32:34] = status.to_bytes(2, "big")

    color = int.from_bytes(
        sfx[_SFX_TAIL_OFF + _SFX_COLOR_REL:_SFX_TAIL_OFF + _SFX_COLOR_REL + 4],
        "big",
    ) & 0xFFFF
    color_off = _SFX_COLOR_WORD_INDEX * 2
    out[color_off:color_off + 2] = color.to_bytes(2, "big")

    # Fill remaining with zeros (SR16 will reinitialize from ROM)
    out[70] = sfx[_SFX_TAIL_OFF + 12] & 0xFF if _SFX_TAIL_OFF + 12 < len(sfx) else 0
    return bytes(out)


def build_sa1_from_chunks(sa1: bytes, sar: bytes) -> bytes | None:
    """Reconstruct SR16 SA1(83B) from snes9x SA1(60B) + SAR(16B)."""
    if len(sar) < SNES_SAR_SIZE:
        return None
    # SA1 section starts with the same register prefix as C01
    out = bytearray(SR16_SA1_SIZE)
    # Copy REG/SAR as the register prefix (first 29 bytes of SA1 = same layout)
    pb, db = sar[0], sar[1]
    p = int.from_bytes(sar[2:4], "big")
    a = int.from_bytes(sar[4:6], "big")
    d = int.from_bytes(sar[6:8], "big")
    s = int.from_bytes(sar[8:10], "big")
    x = int.from_bytes(sar[10:12], "big")
    y = int.from_bytes(sar[12:14], "big")
    pc = int.from_bytes(sar[14:16], "big")
    pc_full = (pb << 16) | pc
    out[SR16_REG_OFF_DB] = db
    out[SR16_REG_OFF_P:SR16_REG_OFF_P + 4] = p.to_bytes(4, "big")
    out[SR16_REG_OFF_A:SR16_REG_OFF_A + 4] = a.to_bytes(4, "big")
    out[SR16_REG_OFF_D:SR16_REG_OFF_D + 4] = d.to_bytes(4, "big")
    out[SR16_REG_OFF_S:SR16_REG_OFF_S + 4] = s.to_bytes(4, "big")
    out[SR16_REG_OFF_X:SR16_REG_OFF_X + 4] = x.to_bytes(4, "big")
    out[SR16_REG_OFF_Y:SR16_REG_OFF_Y + 4] = y.to_bytes(4, "big")
    out[SR16_REG_OFF_PC_FULL:SR16_REG_OFF_PC_FULL + 4] = pc_full.to_bytes(4, "big")
    # Remaining bytes: safe defaults (SR16 will use FillRAM for SA-1 state)
    return bytes(out)


def build_psd_from_dp(name: str, data: bytes) -> bytes | None:
    """Reconstruct SR16 PSD(1450B) from snes9x DP1/DP4 chunk."""
    out = bytearray(SR16_PSD_SIZE)
    if name == "DP1" and len(data) >= _DP1_PAYLOAD_SIZE:
        out[0] = 0x01  # version/selector byte
        out[1:1 + _DP1_PAYLOAD_SIZE] = data[:_DP1_PAYLOAD_SIZE]
    elif name == "DP4" and len(data) >= SNES_DP4_SIZE:
        out[0] = 0x03  # DSP-4 selector
        out[1] = data[0]  # waiting4command
        out[2] = 0       # first_parameter (not used by DSP-4)
        out[3] = data[3] if len(data) > 3 else 0  # command low byte
        out[0x04:0x08] = data[4:8]    # in_count
        out[0x08:0x0C] = data[8:12]   # in_index
        out[0x0C:0x10] = data[12:16]  # out_count
        out[0x10:0x14] = data[16:20]  # out_index
        n = min(len(data) - _DP4_DATA_BASE, _DSP4_BUFFER_SIZE)
        out[_DP4_DATA_BASE:_DP4_DATA_BASE + n] = (
            data[_DP4_DATA_BASE:_DP4_DATA_BASE + n]
        )
    elif name == "DP2" and len(data) >= 1:
        out[0] = 0x02
        n = min(len(data), SR16_PSD_SIZE - 1)
        out[1:1+n] = data[:n]
    else:
        return None
    return bytes(out)


def build_4xc_from_cx4(cx4: bytes) -> bytes | None:
    """SR16 4XC is just raw Cx4 RAM — direct passthrough."""
    if len(cx4) != SR16_4XC_SIZE:
        return None
    return cx4


def optional_sr16_chip_sections(chunks: dict[str, bytes]) -> list[tuple[str, bytes]]:
    """Build SR16 chip sections from snes9x optional chip chunks."""
    sections: list[tuple[str, bytes]] = []
    if "SFX" in chunks:
        sax = build_sax_from_sfx(chunks["SFX"])
        if sax:
            sections.append(("SAX", sax))
    if "SAR" in chunks:
        sa1 = build_sa1_from_chunks(chunks.get("SA1", b""), chunks["SAR"])
        if sa1:
            sections.append(("SA1", sa1))
    for dp_name in ("DP4", "DP1", "DP2"):
        if dp_name in chunks:
            psd = build_psd_from_dp(dp_name, chunks[dp_name])
            if psd:
                sections.append(("PSD", psd))
            break
    if "CX4" in chunks:
        c4 = build_4xc_from_cx4(chunks["CX4"])
        if c4:
            sections.append(("4XC", c4))
    return sections
