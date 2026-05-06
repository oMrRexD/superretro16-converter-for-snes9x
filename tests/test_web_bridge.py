"""Tests for the SaveShift browser/Pyodide bridge."""
from __future__ import annotations

import base64
import gzip

from converter.common.format.snes9x import SNES9X_HEADER, parse_snes9x, write_chunk
from converter.common.constants import SR16_SCREEN_BYTES
from converter.snes9x_to_sr16.format.sr16_writer import build_sr16_blob
from web.python_bridge.web_bridge import (
    _detect_type,
    _frz_output_name,
    _sr16_output_name,
    _slot_output_name,
    dispatch_bytes,
)


def test_info_detects_minimal_sr16_save():
    blob = build_sr16_blob([("TST", b"abc")])

    result = dispatch_bytes("info", "sample.s01", blob)

    assert result["ok"] is True
    assert result["outputName"] == "sample.info.json"
    assert result["info"]["type"] == "sr16"
    assert result["info"]["sections"][0]["code"] == "TST"


def test_extract_sram_uses_s01_and_names_output():
    sram = bytearray(0x20000)
    sram[0:4] = b"SAVE"
    blob = build_sr16_blob([("S01", bytes(sram))])

    result = dispatch_bytes("extract", "Super Metroid.s05", blob)

    assert result["ok"] is True
    assert result["outputName"] == "Super Metroid.srm"
    assert result["outputInfo"]["label"] == "SRAM"
    payload = base64.b64decode(result["dataBase64"])
    assert result["outputInfo"]["size"] == len(payload)
    assert len(payload) == 0x800
    assert payload[:4] == b"SAVE"


def test_extract_sram_uses_snes9x_sra_chunk():
    sram = bytearray(0x80000)
    sram[:4] = b"SNES"
    blob = gzip.compress(SNES9X_HEADER + write_chunk("SRA", bytes(sram)))

    result = dispatch_bytes("extract", "Super Metroid.00.frz", blob)

    assert result["ok"] is True
    assert result["outputName"] == "Super Metroid.srm"
    payload = base64.b64decode(result["dataBase64"])
    assert len(payload) == 0x800
    assert payload[:4] == b"SNES"


def test_info_embeds_sr16_png_preview():
    png = bytearray(SR16_SCREEN_BYTES)
    png[0:2] = b"\x00\xF8"  # RGB565 LE red
    blob = build_sr16_blob([("PNG", bytes(png))])

    result = dispatch_bytes("info", "preview.s01", blob)

    preview = result["info"]["preview"]
    assert preview["source"] == "SR16 PNG"
    assert preview["width"] == 256
    assert preview["height"] == 224
    payload = base64.b64decode(preview["dataUrl"].split(",", 1)[1])
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert payload[16:24] == (256).to_bytes(4, "big") + (224).to_bytes(4, "big")


def test_info_embeds_snes9x_sho_preview():
    sho = bytearray(5 + 2 * 1 * 3)
    sho[0:2] = (2).to_bytes(2, "big")
    sho[2:4] = (1).to_bytes(2, "big")
    sho[5:8] = bytes([31, 0, 0])
    sho[8:11] = bytes([0, 0, 31])
    blob = gzip.compress(SNES9X_HEADER + write_chunk("SHO", bytes(sho)))

    result = dispatch_bytes("info", "preview.000", blob)

    preview = result["info"]["preview"]
    assert preview["source"] == "Snes9X SHO"
    assert preview["width"] == 2
    assert preview["height"] == 1
    payload = base64.b64decode(preview["dataUrl"].split(",", 1)[1])
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert payload[16:24] == (2).to_bytes(4, "big") + (1).to_bytes(4, "big")


def test_invalid_conversion_returns_structured_error():
    result = dispatch_bytes("snes9x-to-sr16", "broken.000", b"not a state")

    assert result["ok"] is False
    assert result["errorType"] in {"ValueError", "EOFError", "OSError"}
    assert result["info"]["type"] == "snes9x"


def test_sr16_slot_output_names_follow_slot_number():
    blob = build_sr16_blob([("TST", b"abc")])

    first = dispatch_bytes("info", "chrono.s01", blob)
    high = dispatch_bytes("info", "chrono.s250", blob)

    assert first["ok"] is True
    assert first["outputName"] == "chrono.info.json"
    assert _slot_output_name("chrono.s01") == "chrono.000"
    assert _slot_output_name("chrono.s25") == "chrono.025"
    assert _slot_output_name("chrono.s250") == "chrono.250"
    assert _slot_output_name("Chrono Trigger_manual(1).s01") == "Chrono Trigger_manual.001"
    # The conversion fails because the synthetic save is incomplete, but
    # best-effort info still validates that .s250 is recognized as SR16.
    assert high["info"]["type"] == "sr16"


def test_snes9x_explus_filenames_are_snes9x_slots():
    assert _detect_type(b"not parsed in this unit", "chrono.00.frz") == "snes9x"
    assert _detect_type(b"not parsed in this unit", "chrono.10.frz") == "snes9x"
    assert _detect_type(b"not parsed in this unit", "chrono.frz") == "unknown"
    assert _sr16_output_name("chrono.00.frz") == "chrono.s01"
    assert _sr16_output_name("chrono.10.frz") == "chrono.s10"


def test_sr16_to_snes9x_explus_output_names_follow_slot_number():
    assert _frz_output_name("chrono.s01") == "chrono.00.frz"
    assert _frz_output_name("chrono.s25") == "chrono.25.frz"
    assert _frz_output_name("chrono.s250") == "chrono.250.frz"
    assert _frz_output_name("Chrono Trigger_manual(1).s01") == "Chrono Trigger_manual.01.frz"


def test_sr16_to_snes9x_explus_dispatch_uses_frz_name_for_valid_errors():
    blob = build_sr16_blob([("TST", b"abc")])

    result = dispatch_bytes("sr16-to-snes9x-explus", "chrono.s25", blob)

    # The synthetic SR16 blob is structurally incomplete for conversion, but
    # the public action must be accepted by the bridge instead of returning
    # "Unsupported action".
    assert result["ok"] is False
    assert "Unsupported action" not in result["error"]
    assert result["info"]["type"] == "sr16"


def test_snes9x_to_explus_strips_optional_sho_chunk():
    blob = gzip.compress(
        SNES9X_HEADER
        + write_chunk("CPU", b"cpu")
        + write_chunk("SHO", b"preview")
        + write_chunk("RAM", b"ram")
    )

    result = dispatch_bytes("snes9x-to-snes9x-explus", "chrono.000", blob)

    assert result["ok"] is True
    assert result["outputName"] == "chrono.00.frz"
    payload = base64.b64decode(result["dataBase64"])
    assert result["outputInfo"]["label"] == "Snes9X EX+ save state"
    assert result["outputInfo"]["size"] == len(payload)
    chunks = parse_snes9x(payload)
    assert list(chunks) == ["CPU", "RAM"]


def test_snes9x_explus_to_regular_slot_name():
    blob = gzip.compress(SNES9X_HEADER + write_chunk("CPU", b"cpu"))

    result = dispatch_bytes("snes9x-explus-to-snes9x", "chrono.10.frz", blob)

    assert result["ok"] is True
    assert result["outputName"] == "chrono.010"
    assert result["outputInfo"]["label"] == "Snes9X save state"
    assert result["outputInfo"]["size"] == len(base64.b64decode(result["dataBase64"]))
