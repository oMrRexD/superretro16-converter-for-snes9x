"""Tests for SR16 D01 -> snes9x DMA remapping."""
from __future__ import annotations

from converter.sr16_to_snes9x.state.dma import _extract_dma
from converter.common.constants import (
    SR16_D01_SIZE, SR16_F01_SIZE,
    HDMAEN, DMA_REGS_BASE,
)


def test_extract_dma_keeps_hdma_indirect_address_big_endian_and_marks_transfer():
    d01 = bytearray(SR16_D01_SIZE)
    # Channel 0 D01 fields: AAddress=0x8000, Address=0x7E80,
    # BAddress=$31, DMACount/indirect address=0x8300.
    d01[3] = 0
    d01[4] = 0x7E
    d01[5:7] = b"\x80\x00"
    d01[7:9] = b"\x7E\x80"
    d01[9] = 0x31
    d01[11:13] = b"\x83\x00"
    d01[13] = 0x7E
    d01[16] = 1
    d01[17] = 0xFF

    f01 = bytearray(SR16_F01_SIZE)
    f01[HDMAEN] = 0x01
    f01[DMA_REGS_BASE:DMA_REGS_BASE + 8] = bytes.fromhex("403100807e43437e")

    out = _extract_dma(bytes(d01), bytes(f01))

    assert out[10:12] == b"\x83\x00"
    assert out[18] == 1
