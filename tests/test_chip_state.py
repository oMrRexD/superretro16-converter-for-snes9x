"""Tests for chip_state translators."""
from __future__ import annotations

from converter.sr16_to_snes9x.chips.state import (
    _reg_from_sr16_register_prefix,
    _default_dp4_chunk, _drain_dp4_chunk,
    _dsp_payload_from_sr16_psd,
    _build_sfx_chunk_from_sax,
    _source_title,
    _dsp_chunk_name_for_sr16_psd,
    _optional_chip_chunks_from_sr16,
)
from converter.common.constants import (
    SNES_DP4_SIZE, SNES_REG_SIZE, SNES_SFX_SIZE,
    SR16_PSD_SIZE, SR16_SAX_SIZE,
)
from converter.common.format.sr16 import SR16Save, SR16Section
from converter.sr16_to_snes9x.game_registry import chip_stubs_for_source


# ---------------------------------------------------------------------------
# _reg_from_sr16_register_prefix
# ---------------------------------------------------------------------------

def test_reg_from_sr16_register_prefix_short_returns_zeros():
    assert _reg_from_sr16_register_prefix(b"") == b"\x00" * SNES_REG_SIZE
    assert _reg_from_sr16_register_prefix(b"\x00" * 8) == b"\x00" * SNES_REG_SIZE


def test_reg_from_sr16_register_prefix_packs_pb_db_pc():
    prefix = bytearray(0x20)
    prefix[0x00] = 0x33                                   # DB
    prefix[0x01:0x05] = (0x0001).to_bytes(4, "big")       # P
    prefix[0x19:0x1D] = (0x82DEAD).to_bytes(4, "big")     # PB|PC: PB=0x82, PC=0xDEAD
    out = _reg_from_sr16_register_prefix(bytes(prefix))
    assert len(out) == SNES_REG_SIZE
    assert out[0] == 0x82                                 # PB
    assert out[1] == 0x33                                 # DB
    assert out[14:16] == (0xDEAD).to_bytes(2, "big")      # PC


# ---------------------------------------------------------------------------
# DP4 helpers
# ---------------------------------------------------------------------------

def test_default_dp4_chunk_has_only_waiting4command_set():
    chunk = _default_dp4_chunk()
    assert len(chunk) == SNES_DP4_SIZE
    assert chunk[0] == 1
    # All other bytes zero
    assert all(b == 0 for b in chunk[1:])


def test_drain_dp4_chunk_sets_out_count_to_512():
    chunk = _drain_dp4_chunk()
    assert len(chunk) == SNES_DP4_SIZE
    # waiting4command=1, half_command=0, command(2)=0, in_count(4)=0, in_index(4)=0
    assert chunk[0] == 1
    assert chunk[1] == 0
    assert chunk[2:4] == b"\x00\x00"
    assert chunk[4:8] == b"\x00\x00\x00\x00"
    assert chunk[8:12] == b"\x00\x00\x00\x00"
    # out_count = 512 (BE)
    assert int.from_bytes(chunk[12:16], "big") == 512
    # out_index = 0
    assert int.from_bytes(chunk[16:20], "big") == 0


def test_dp4_payload_idle_psd_returns_default_without_cpu_context():
    psd = bytearray(SR16_PSD_SIZE)
    psd[0] = 0x03                  # version
    psd[1] = 1                     # waiting4command=TRUE
    out = _dsp_payload_from_sr16_psd("DP4", bytes(psd))
    assert out == _default_dp4_chunk()


def test_dp4_payload_with_pending_output_carries_state():
    psd = bytearray(SR16_PSD_SIZE)
    psd[0] = 0x03
    psd[1] = 1                     # waiting4command
    psd[3] = 0x42                  # command low byte
    psd[0x0C:0x10] = (16).to_bytes(4, "big")   # out_count=16
    psd[0x10:0x14] = (4).to_bytes(4, "big")    # out_index=4
    psd[0x214:0x224] = bytes(range(16))         # 16 bytes of pending output
    out = _dsp_payload_from_sr16_psd("DP4", bytes(psd))
    assert len(out) == SNES_DP4_SIZE
    assert out[0] == 1                          # waiting4command
    assert int.from_bytes(out[2:4], "big") == 0x42  # command (8b promoted)
    assert int.from_bytes(out[12:16], "big") == 16
    assert int.from_bytes(out[16:20], "big") == 4
    assert out[0x214:0x224] == bytes(range(16))


def test_dp1_payload_strips_leading_selector_byte():
    psd = bytes([0x03]) + bytes(range(256)) * 5 + b"\x00" * (SR16_PSD_SIZE - 1281)
    psd = psd[:SR16_PSD_SIZE]
    out = _dsp_payload_from_sr16_psd("DP1", psd)
    assert out == psd[1:]


# ---------------------------------------------------------------------------
# _build_sfx_chunk_from_sax
# ---------------------------------------------------------------------------

def test_sfx_returns_none_for_wrong_size():
    assert _build_sfx_chunk_from_sax(b"") is None
    assert _build_sfx_chunk_from_sax(b"\x00" * 32) is None


def test_sfx_basic_size():
    sax = b"\x00" * SR16_SAX_SIZE
    out = _build_sfx_chunk_from_sax(sax)
    assert out is not None
    assert len(out) == SNES_SFX_SIZE


def test_sfx_accepts_observed_padded_sax_size():
    sax = b"\x00" * (SR16_SAX_SIZE + 2)
    out = _build_sfx_chunk_from_sax(sax)
    assert out is not None
    assert len(out) == SNES_SFX_SIZE


# ---------------------------------------------------------------------------
# Structural optional chip emission
# ---------------------------------------------------------------------------

def test_source_title_url_decodes_and_lowercases():
    sr16 = SR16Save(sections=[], trailer=b"", source_name="Top%20Gear%203000.s01")
    assert _source_title(sr16) == "top gear 3000.s01"


def test_psd_dispatch_defaults_to_dp1_without_title_matching():
    sr16 = SR16Save(sections=[], trailer=b"",
                    source_name="Top%20Gear%203000%20(USA).s01")
    assert _dsp_chunk_name_for_sr16_psd(sr16) == "DP1"


def test_idle_placeholder_psd_dispatches_to_dp4_without_title_matching():
    psd = bytearray(SR16_PSD_SIZE)
    psd[0] = 0x03
    psd[1] = 1
    psd[2] = 1
    sr16 = SR16Save(
        sections=[SR16Section("PSD", len(psd), 0, bytes(psd))],
        trailer=b"",
        source_name="renamed-save-with-no-game-title.s01",
    )
    chunks = dict(_optional_chip_chunks_from_sr16(sr16))
    assert "DP4" in chunks
    assert "DP1" not in chunks
    assert "DP2" not in chunks
    assert chunks["DP4"] == _default_dp4_chunk()


def test_idle_dp4_psd_drains_only_when_cpu_is_in_dsp4_io_routine():
    psd = bytearray(SR16_PSD_SIZE)
    psd[0] = 0x03
    psd[1] = 1
    psd[2] = 1
    c01 = bytearray(0xA1)
    c01[0x00] = 0x30
    c01[0x19:0x1D] = (0x82D151).to_bytes(4, "big")
    sr16 = SR16Save(
        sections=[
            SR16Section("C01", len(c01), 0, bytes(c01)),
            SR16Section("PSD", len(psd), 0, bytes(psd)),
        ],
        trailer=b"",
        source_name="renamed-save-with-no-game-title.s01",
    )
    chunks = dict(_optional_chip_chunks_from_sr16(sr16))
    assert chunks["DP4"] == _drain_dp4_chunk()


def test_pending_dp4_shaped_psd_dispatches_to_dp4():
    psd = bytearray(SR16_PSD_SIZE)
    psd[0] = 0x03
    psd[1] = 1
    psd[2] = 1
    psd[0x0C:0x10] = (16).to_bytes(4, "big")
    psd[0x10:0x14] = (4).to_bytes(4, "big")
    sr16 = SR16Save(
        sections=[SR16Section("PSD", len(psd), 0, bytes(psd))],
        trailer=b"",
        source_name="renamed-save-with-no-game-title.s01",
    )
    chunks = dict(_optional_chip_chunks_from_sr16(sr16))
    assert "DP4" in chunks
    assert "DP1" not in chunks


def test_non_placeholder_psd_emits_only_dp1_without_title_matching():
    psd = bytearray(SR16_PSD_SIZE)
    psd[0] = 0x00
    psd[1] = 1
    psd[3] = 0x28
    sr16 = SR16Save(
        sections=[SR16Section("PSD", len(psd), 0, bytes(psd))],
        trailer=b"",
        source_name="renamed-save-with-no-game-title.s01",
    )
    chunks = dict(_optional_chip_chunks_from_sr16(sr16))
    assert "DP1" in chunks
    assert "DP2" not in chunks
    assert "DP4" not in chunks
    assert chunks["DP1"] == bytes(psd)[1:]


def test_no_global_compatibility_stubs_for_plain_save():
    sr16 = SR16Save(sections=[], trailer=b"",
                    source_name="plain-normal-game.s01")
    chunks = dict(_optional_chip_chunks_from_sr16(sr16))
    assert chunks == {}


def test_srtc_stub_is_rom_header_driven(tmp_path):
    rom = bytearray(0x10000)
    header = 0x7FC0
    rom[header:header + 21] = b"STRUCTURAL SRTC TEST ".ljust(21)
    rom[header + 0x15] = 0x35
    rom[header + 0x16] = 0x55
    rom[header + 0x1C:header + 0x1E] = (0x1234).to_bytes(2, "little")
    rom[header + 0x1E:header + 0x20] = (0xEDCB).to_bytes(2, "little")
    rom_path = tmp_path / "sample.sfc"
    rom_path.write_bytes(rom)
    save_path = tmp_path / "sample.s01"
    assert [name for name, _size in chip_stubs_for_source(str(save_path))] == [
        "SRT", "CLK",
    ]
