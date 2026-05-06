"""Tests for the snes9x → SuperRetro16 reverse converter."""
from __future__ import annotations
import gzip
import pytest
import struct

from converter.cli import main as converter_main
from converter.common.format.sr16 import decode_marker, parse_sr16, SR16_MAGIC, MARKER_LEN
from converter.common.format.snes9x import SNES9X_HEADER, write_chunk
from converter.common.constants import (
    SR16_C01_SIZE, SR16_D01_SIZE, SR16_SSZ_SIZE,
    SNES_CPU_SIZE, SNES_REG_SIZE, SNES_TIM_SIZE,
    SNES_PPU_SIZE, SNES_DMA_SIZE, SNES_SND_SIZE,
    PPU_OFF_CGDATA, SR16_SCREEN_BYTES, SHO_DATA_BYTES,
    SR16_RM1_SIZE, SRAM_TARGET_SIZE,
)
from converter.snes9x_to_sr16.format.sr16_writer import encode_marker, build_sr16_blob
from converter.snes9x_to_sr16.state.cpu import build_c01, _sr16_opcode_table_selector
from converter.snes9x_to_sr16.state.dma import build_d01
from converter.snes9x_to_sr16.state.ppu import build_p01
from converter.snes9x_to_sr16.state.palette import (
    bgr555_to_rgb565,
    encode_cgram_to_sr16,
    patch_p01_cgdata_as_rgb565,
)
from converter.snes9x_to_sr16.state.audio import build_a01, build_ar1, build_ssz
from converter.snes9x_to_sr16.state.screenshot import build_png_from_sho


# ============================================================================
# Marker codec
# ============================================================================

class TestMarkerCodec:
    @pytest.mark.parametrize("code,size", [
        ("C01", 161), ("P01", 2645), ("D01", 152),
        ("VR1", 65536), ("RM1", 131072), ("F01", 32768),
        ("A01", 248), ("AR1", 65536), ("SSZ", 1281),
        ("PSD", 1450), ("4XC", 8192), ("PNG", 114688),
    ])
    def test_encode_decode_roundtrip(self, code, size):
        encoded = encode_marker(code, size)
        assert len(encoded) == MARKER_LEN
        decoded = decode_marker(encoded)
        assert decoded == f"{code}_{size:06d}_"

    def test_build_sr16_blob_structure(self):
        sections = [
            ("TST", b"\x01\x02\x03"),
            ("AB2", b"\xFF" * 10),
        ]
        blob = build_sr16_blob(sections)
        assert blob.startswith(SR16_MAGIC)
        save = parse_sr16(blob)
        assert len(save.sections) == 2
        assert save.sections[0].code == "TST"
        assert save.sections[0].data == b"\x01\x02\x03"
        assert save.sections[1].code == "AB2"
        assert save.sections[1].data == b"\xFF" * 10

    @pytest.mark.parametrize("code,size", [
        ("TOO_LONG", 1),
        ("AB", 1),
        ("TST", -1),
        ("TST", 1_000_000),
    ])
    def test_encode_marker_rejects_invalid_marker_fields(self, code, size):
        with pytest.raises(ValueError):
            encode_marker(code, size)

# ============================================================================
# CPU / REG / TIM → C01
# ============================================================================

class TestCpuReverse:
    def _make_reg(self, pb=0, db=0, p=0, a=0, d=0, s=0x1FF, x=0, y=0, pc=0):
        out = bytearray(SNES_REG_SIZE)
        out[0] = pb; out[1] = db
        out[2:4] = p.to_bytes(2, "big")
        out[4:6] = a.to_bytes(2, "big")
        out[6:8] = d.to_bytes(2, "big")
        out[8:10] = s.to_bytes(2, "big")
        out[10:12] = x.to_bytes(2, "big")
        out[12:14] = y.to_bytes(2, "big")
        out[14:16] = pc.to_bytes(2, "big")
        return bytes(out)

    def _make_cpu(self, cycles=0, v_counter=0, fast_rom=8):
        out = bytearray(SNES_CPU_SIZE)
        out[0:4] = cycles.to_bytes(4, "big")
        out[4:8] = (182).to_bytes(4, "big")  # PrevCycles
        out[8:12] = v_counter.to_bytes(4, "big")
        out[28:32] = fast_rom.to_bytes(4, "big")
        return bytes(out)

    def _make_tim(self, h_max=1364, v_max_m=262, v_max=262):
        out = bytearray(SNES_TIM_SIZE)
        out[0:4] = h_max.to_bytes(4, "big")     # H_Max_Master
        out[4:8] = h_max.to_bytes(4, "big")      # H_Max
        out[8:12] = v_max_m.to_bytes(4, "big")   # V_Max_Master
        out[12:16] = v_max.to_bytes(4, "big")     # V_Max
        return bytes(out)

    def test_c01_size(self):
        c01 = build_c01(self._make_cpu(), self._make_reg(), self._make_tim())
        assert len(c01) == SR16_C01_SIZE

    def test_c01_registers_roundtrip(self):
        reg = self._make_reg(pb=0x81, db=0x8C, a=0x00AA, s=0x1FEE, x=0x2C, y=0x87D6, pc=0x87FC)
        c01 = build_c01(self._make_cpu(), reg, self._make_tim())
        # Check PB:PC combined field
        pc_full = int.from_bytes(c01[0x19:0x1D], "big")
        assert (pc_full >> 16) & 0xFF == 0x81  # PB
        assert pc_full & 0xFFFF == 0x87FC      # PC
        assert c01[0x00] == 0x8C               # DB

    @pytest.mark.parametrize("p,selector", [
        (0x0030, 0x00000000),  # native M=1/X=1
        (0x0134, 0x00000100),  # emulation mode overrides M/X
        (0x0024, 0x00000200),  # M=1/X=0
        (0x0080, 0x00000300),  # M=0/X=0
        (0x0010, 0x00000400),  # M=0/X=1
    ])
    def test_c01_opcode_table_selector_matches_sr16_modes(self, p, selector):
        assert _sr16_opcode_table_selector(p) == selector
        reg = self._make_reg(p=p)
        c01 = build_c01(self._make_cpu(), reg, self._make_tim())
        assert int.from_bytes(c01[0x69:0x6D], "big") == selector


# ============================================================================
# DMA reverse
# ============================================================================

class TestDmaReverse:
    def test_hdma_booleans_use_native_sr16_field_order(self):
        """SnapDMA's HDMAI/AAD/DoTransfer order is not SR16's D01 order."""
        dma = bytearray(SNES_DMA_SIZE)
        si = 7 * 19
        dma[si+0] = 0        # ReverseTransfer
        dma[si+1] = 1        # HDMAIndirectAddressing
        dma[si+2] = 0        # UnusedBit43x0
        dma[si+3] = 0        # AAddressFixed
        dma[si+4] = 0        # AAddressDecrement
        dma[si+5] = 3        # TransferMode
        dma[si+6] = 0x11     # BAddress
        dma[si+7:si+9] = b"\xD8\x6F"
        dma[si+9] = 0x88
        dma[si+10:si+12] = b"\x55\x00"
        dma[si+12] = 0x7E
        dma[si+13:si+15] = b"\xD8\xD1"
        dma[si+15] = 0
        dma[si+16] = 0x80
        dma[si+17] = 0xFF
        dma[si+18] = 1       # SnapDMA active HDMA flag

        d01 = build_d01(bytes(dma))
        ch7 = d01[7 * 19:8 * 19]

        assert ch7.hex() == "0000000388d86fd8d1110155007e008000ff00"


# ============================================================================
# Palette conversion
# ============================================================================

class TestPaletteReverse:
    def test_bgr555_to_rgb565_black(self):
        assert bgr555_to_rgb565(0x0000) == 0x0000

    def test_bgr555_to_rgb565_white(self):
        # BGR555 white = 0x7FFF → R=31, G=31→63, B=31 → RGB565 = 0xFFFF
        assert bgr555_to_rgb565(0x7FFF) == 0xFFFF

    def test_bgr555_to_rgb565_pure_red(self):
        # BGR555: 0BBBBBGGGGGRRRRR → pure red = 0x001F
        # RGB565: RRRRRGGG GGGBBBBB → (31<<11) = 0xF800
        assert bgr555_to_rgb565(0x001F) == 0xF800

    def test_bgr555_to_rgb565_pure_blue(self):
        # BGR555: pure blue = 0x7C00 → B=31
        # RGB565: (0<<11) | (0<<5) | 31 = 0x001F
        assert bgr555_to_rgb565(0x7C00) == 0x001F

    def test_encode_cgram_to_sr16_uses_p01_big_endian_cache(self):
        """P01 CGDATA is RGB565, but not the little-endian PNG byte order."""
        ppu = bytearray(SNES_PPU_SIZE)
        # CGDATA[1] = pure red in snes9x raw BGR555.
        ppu[PPU_OFF_CGDATA + 2:PPU_OFF_CGDATA + 4] = (0x001F).to_bytes(2, "big")
        encoded = encode_cgram_to_sr16(bytes(ppu))
        assert encoded[2:4] == b"\xF8\x00"

    def test_patch_p01_cgdata_loads_freezedata_from_new_converter_reverse_location(self):
        p01 = bytearray(2645)
        ppu = bytearray(SNES_PPU_SIZE)
        ppu[PPU_OFF_CGDATA + 2:PPU_OFF_CGDATA + 4] = (0x001F).to_bytes(2, "big")

        patch_p01_cgdata_as_rgb565(p01, bytes(ppu))

        assert b"\xF8\x00" in p01


# ============================================================================
# PPU reverse
# ============================================================================

class TestPpuReverse:
    def test_build_p01_loads_freezedata_from_new_converter_reverse_location(self):
        p01 = build_p01(b"\x00" * SNES_PPU_SIZE)

        assert len(p01) == 2645


# ============================================================================
# SHO screenshot → SR16 PNG framebuffer
# ============================================================================

class TestScreenshotReverse:
    def test_build_png_from_sho_uses_interlace_byte_then_compact_pixels(self):
        sho = bytearray(5 + SHO_DATA_BYTES)
        sho[0:2] = (256).to_bytes(2, "big")
        sho[2:4] = (224).to_bytes(2, "big")
        sho[4] = 1  # interlace flag; must not be read as pixel data

        # Pixel (0,0): pure red in SHO's R5/G5/B5 triplet.
        sho[5:8] = bytes([31, 0, 0])

        # Pixel (0,1): pure blue.  This catches the old 512-wide stride bug:
        # snes9x SHO rows in our saves are compact by the saved width.
        row1 = 5 + 256 * 3
        sho[row1:row1 + 3] = bytes([0, 0, 31])

        png = build_png_from_sho(bytes(sho))

        assert png is not None
        assert len(png) == SR16_SCREEN_BYTES
        assert png[0:2] == b"\x00\xF8"  # RGB565 LE red
        assert png[256 * 2:256 * 2 + 2] == b"\x1F\x00"  # RGB565 LE blue


# ============================================================================
# Audio reverse
# ============================================================================

class TestAudioReverse:
    def _make_snd(self):
        """Create a minimal valid SND chunk (66560B)."""
        return b"\x00" * SNES_SND_SIZE

    def test_a01_size(self):
        a01 = build_a01(self._make_snd())
        assert len(a01) == 248

    def test_ar1_size(self):
        ar1 = build_ar1(self._make_snd())
        assert len(ar1) == 65536

    def test_ssz_size(self):
        ssz = build_ssz(self._make_snd())
        assert len(ssz) == SR16_SSZ_SIZE


# ============================================================================
# Full structural roundtrip
# ============================================================================

class TestStructuralRoundtrip:
    def test_build_and_parse_sr16(self):
        """A built SR16 blob should be parseable."""
        sections = [
            ("C01", b"\x00" * 161),
            ("P01", b"\x00" * 2645),
            ("D01", b"\x00" * 152),
            ("VR1", b"\x00" * 65536),
            ("RM1", b"\x00" * 131072),
            ("S01", b"\x00" * 131072),
            ("F01", b"\x00" * 32768),
            ("A01", b"\x00" * 248),
            ("AR1", b"\x00" * 65536),
        ]
        blob = build_sr16_blob(sections)
        save = parse_sr16(blob)
        assert len(save.sections) == 9
        codes = [s.code for s in save.sections]
        assert codes == ["C01", "P01", "D01", "VR1", "RM1", "S01", "F01", "A01", "AR1"]
        for s in save.sections:
            expected = next(size for code, data in sections if code == s.code for size in [len(data)])
            assert s.size == expected

    def test_auto_cli_autodetects_snes9x_input_and_writes_sr16(self, tmp_path):
        plain = bytearray(SNES9X_HEADER)
        for code, data in (
            ("CPU", b"\x00" * SNES_CPU_SIZE),
            ("REG", b"\x00" * SNES_REG_SIZE),
            ("PPU", b"\x00" * SNES_PPU_SIZE),
            ("DMA", b"\x00" * SNES_DMA_SIZE),
            ("VRA", b"\x00" * 0x10000),
            ("RAM", b"\x00" * SR16_RM1_SIZE),
            ("SRA", b"\x00" * SRAM_TARGET_SIZE),
            ("FIL", b"\x00" * 0x8000),
            ("SND", b"\x00" * SNES_SND_SIZE),
            ("TIM", b"\x00" * SNES_TIM_SIZE),
        ):
            plain += write_chunk(code, data)

        src = tmp_path / "input.000"
        dst = tmp_path / "output.s08"
        src.write_bytes(gzip.compress(bytes(plain)))

        converter_main([str(src), str(dst)])

        save = parse_sr16(dst.read_bytes())
        assert save.by_code("C01") is not None
        assert save.by_code("P01") is not None
        assert save.by_code("SSZ") is not None
