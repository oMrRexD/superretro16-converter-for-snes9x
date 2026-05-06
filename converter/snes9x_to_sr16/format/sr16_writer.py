"""SuperRetro16 .s0X binary writer: marker encoder + blob assembler.

The SR16 save format uses 11-byte XOR-encoded markers before each section.
This module provides the inverse of ``converter.common.format.sr16.decode_marker``.
"""
from __future__ import annotations

from converter.common.format.sr16 import MARKER_KEYS, MARKER_LEN, SR16_MAGIC


def encode_marker(code: str, size: int) -> bytes:
    """Encode a 3-char section code and size into an 11-byte SR16 marker.

    The plaintext marker is ``"CCC_SSSSSS_"`` where CCC is the 3-letter code
    and SSSSSS is the 6-digit zero-padded decimal size.
    """
    if len(code) != 3:
        raise ValueError(f"SR16 section code must be 3 characters: {code!r}")
    if not 0 <= size <= 999999:
        raise ValueError(f"SR16 section size out of marker range: {size}")

    plain = f"{code}_{size:06d}_"
    out = bytearray(MARKER_LEN)
    for i, ch in enumerate(plain):
        b = ord(ch)
        if i == 0 or b == 0:
            out[i] = b
        else:
            out[i] = b ^ MARKER_KEYS[i]
    return bytes(out)


def build_sr16_blob(sections: list[tuple[str, bytes]]) -> bytes:
    """Assemble a full SR16 .s0X file from a list of (code, data) pairs.

    Section order should match SR16's own serialization order:
      C01, P01, D01, VR1, RM1, S01, F01, A01, AR1, SSZ, [chips], PNG
    """
    out = bytearray(SR16_MAGIC)
    for code, data in sections:
        out += encode_marker(code, len(data))
        out += data
    return bytes(out)
