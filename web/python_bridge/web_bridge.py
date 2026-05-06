"""Browser-facing bridge for SaveShift's Pyodide worker.

The JavaScript worker writes the uploaded file into Pyodide's virtual
filesystem, calls ``dispatch_file()``, and receives a JSON string.  Binary
outputs are base64-encoded so the JS side can rebuild a Blob without exposing
Python objects directly.
"""
from __future__ import annotations

import base64
import binascii
import gzip
import json
import os
import re
import struct
import tempfile
import warnings
import zlib
from pathlib import Path
from typing import Any

from converter.common.constants import (
    SHO_MAX_HEIGHT,
    SHO_MAX_WIDTH,
    SR16_SCREEN_BYTES,
    SR16_SCREEN_HEIGHT,
    SR16_SCREEN_WIDTH,
)
from converter.common.format.snes9x import SNES9X_HEADER, parse_snes9x, write_chunk
from converter.common.format.sr16 import SR16_MAGIC_PREFIX, parse_sr16
from converter.sr16_to_snes9x.pipeline import build_snes9x, extract_chunks_from_sr16


SLOT_EXTENSIONS = {f".{i:03d}" for i in range(1000)}


def dispatch_file(action: str, filename: str, input_path: str) -> str:
    """Read ``input_path`` and return a JSON response string."""
    with open(input_path, "rb") as f:
        data = f.read()
    return json.dumps(dispatch_bytes(action, filename, data), ensure_ascii=False)


def dispatch_bytes(action: str, filename: str, data: bytes) -> dict[str, Any]:
    """Dispatch an action and always return a JSON-serializable dict."""
    try:
        if action == "sr16-to-snes9x":
            return _file_response(
                _convert_sr16_to_snes9x(data, filename),
                _slot_output_name(filename),
                "application/octet-stream",
                _inspect(data, filename),
            )
        if action == "sr16-to-snes9x-explus":
            return _file_response(
                _strip_snes9x_sho(_convert_sr16_to_snes9x(data, filename)),
                _frz_output_name(filename),
                "application/octet-stream",
                _inspect(data, filename),
            )
        if action == "snes9x-to-snes9x-explus":
            return _file_response(
                _strip_snes9x_sho(data),
                _frz_from_snes9x_output_name(filename),
                "application/octet-stream",
                _inspect(data, filename),
            )
        if action == "snes9x-explus-to-snes9x":
            return _file_response(
                data,
                _slot_from_snes9x_output_name(filename),
                "application/octet-stream",
                _inspect(data, filename),
            )
        if action == "snes9x-to-sr16":
            return _file_response(
                _convert_snes9x_to_sr16(data, filename),
                _sr16_output_name(filename),
                "application/octet-stream",
                _inspect(data, filename),
            )
        if action == "extract":
            return _file_response(
                _extract_sram(data, filename),
                _sram_output_name(filename),
                "application/octet-stream",
                _inspect(data, filename),
            )
        if action == "info":
            info = _inspect(data, filename)
            payload = json.dumps(info, ensure_ascii=False, indent=2).encode("utf-8")
            return _file_response(
                payload,
                _info_output_name(filename),
                "application/json",
                info,
            )
        raise ValueError(f"Unsupported action: {action}")
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "errorType": type(exc).__name__,
            "info": _best_effort_info(data, filename),
        }


def _file_response(payload: bytes, output_name: str, mime: str,
                   info: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "outputName": output_name,
        "mime": mime,
        "size": len(payload),
        "dataBase64": base64.b64encode(payload).decode("ascii"),
        "info": info,
        "outputInfo": _output_info(payload, output_name, mime),
    }


def _output_info(payload: bytes, output_name: str, mime: str) -> dict[str, Any]:
    lower = output_name.lower()
    if lower.endswith(".frz"):
        out_type = "snes9x-explus"
        label = "Snes9X EX+ save state"
    elif _snes9x_slot_from_name(output_name) is not None:
        out_type = "snes9x"
        label = "Snes9X save state"
    elif _sr16_slot_from_suffix(Path(output_name).suffix.lower()) is not None:
        out_type = "sr16"
        label = "SuperRetro16 save state"
    elif lower.endswith(".srm"):
        out_type = "sram"
        label = "SRAM"
    elif mime == "application/json" or lower.endswith(".json"):
        out_type = "json"
        label = "JSON"
    else:
        out_type = "binary"
        label = "Binary file"
    return {
        "type": out_type,
        "label": label,
        "filename": output_name,
        "size": len(payload),
        "crc32": _crc32_hex(payload),
    }


def _convert_sr16_to_snes9x(data: bytes, filename: str) -> bytes:
    sr16 = parse_sr16(data, filename)
    chunks = extract_chunks_from_sr16(sr16)
    plain = build_snes9x(sr16, chunks)
    return gzip.compress(plain, compresslevel=6, mtime=0)


def _strip_snes9x_sho(data: bytes) -> bytes:
    """Return a snes9x snapshot without the optional screenshot chunk."""
    chunks = parse_snes9x(data)
    if "SHO" not in chunks:
        return data
    plain = bytearray(SNES9X_HEADER)
    for code, payload in chunks.items():
        if code != "SHO":
            plain += write_chunk(code, payload)
    return gzip.compress(bytes(plain), compresslevel=6, mtime=0)


def _convert_snes9x_to_sr16(data: bytes, filename: str) -> bytes:
    from converter.snes9x_to_sr16.pipeline import snes9x_to_sr16

    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "input.state"
        dst = Path(td) / "output.s01"
        src.write_bytes(data)
        snes9x_to_sr16(str(src), str(dst))
        return dst.read_bytes()


def _extract_sram(data: bytes, filename: str) -> bytes:
    detected = _detect_type(data, filename)
    if detected == "sr16":
        sr16 = parse_sr16(data, filename)
        section = sr16.by_code("S01")
        if section is None:
            raise ValueError("SR16 save has no S01/SRAM section")
        return _trim_sram(section.data)
    if detected == "snes9x":
        chunks = parse_snes9x(data)
        sra = chunks.get("SRA")
        if sra is None:
            raise ValueError("Snes9X save has no SRA/SRAM chunk")
        return _trim_sram(sra)
    raise ValueError("SRAM extraction requires an SR16 or Snes9X save state")


def _trim_sram(data: bytes) -> bytes:
    sram = bytearray(data)
    last_nz = len(sram) - 1
    while last_nz > 0 and sram[last_nz] == 0:
        last_nz -= 1
    actual = last_nz + 1
    for boundary in (0x800, 0x2000, 0x8000, 0x10000, 0x20000):
        if actual <= boundary:
            actual = boundary
            break
    return bytes(sram[:actual])


def _inspect(data: bytes, filename: str) -> dict[str, Any]:
    warnings_list: list[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        detected = _detect_type(data, filename)
        if detected == "sr16":
            save = parse_sr16(data, filename, lenient=True)
            preview = _preview_from_sr16_save(save)
            sections = [
                {
                    "code": section.code,
                    "size": section.size,
                    "offset": section.offset,
                }
                for section in save.sections
            ]
            for w in caught:
                warnings_list.append(str(w.message))
            return {
                "type": "sr16",
                "label": "SuperRetro16 save state",
                "filename": filename,
                "size": len(data),
                "crc32": _crc32_hex(data),
                "sections": sections,
                "trailerBytes": len(save.trailer),
                "preview": preview,
                "warnings": warnings_list,
            }
        if detected == "snes9x":
            chunks = parse_snes9x(data)
            preview = _preview_from_snes9x_chunks(chunks)
            return {
                "type": "snes9x",
                "label": "Snes9X save state",
                "filename": filename,
                "size": len(data),
                "crc32": _crc32_hex(data),
                "chunks": [
                    {"code": code, "size": len(payload)}
                    for code, payload in chunks.items()
                ],
                "preview": preview,
                "warnings": warnings_list,
            }
        return {
            "type": detected,
            "label": "Raw SRAM / unknown binary" if detected == "sram" else "Unknown binary",
            "filename": filename,
            "size": len(data),
            "crc32": _crc32_hex(data),
            "warnings": warnings_list,
        }


def _best_effort_info(data: bytes, filename: str) -> dict[str, Any]:
    try:
        return _inspect(data, filename)
    except Exception:
        return {
            "type": _detect_type(data, filename),
            "filename": filename,
            "size": len(data),
            "crc32": _crc32_hex(data),
            "warnings": [],
        }


def _detect_type(data: bytes, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if data.startswith(SR16_MAGIC_PREFIX) or _sr16_slot_from_suffix(ext) is not None:
        return "sr16"
    if (data.startswith(b"#!s9xsnp:") or data.startswith(b"\x1f\x8b")
            or ext in SLOT_EXTENSIONS
            or _snes9x_explus_slot_from_name(filename) is not None):
        return "snes9x"
    return "unknown"


def _crc32_hex(data: bytes) -> str:
    return f"{binascii.crc32(data) & 0xFFFFFFFF:08X}"


def _preview_from_sr16_save(save) -> dict[str, Any] | None:
    section = save.by_code("PNG")
    if section is None or len(section.data) != SR16_SCREEN_BYTES:
        return None
    return _preview_from_rgb565(section.data, SR16_SCREEN_WIDTH, SR16_SCREEN_HEIGHT, "SR16 PNG")


def _preview_from_snes9x_chunks(chunks: dict[str, bytes]) -> dict[str, Any] | None:
    sho = chunks.get("SHO")
    if not sho:
        return None
    return _preview_from_sho(sho)


def _preview_from_rgb565(data: bytes, width: int, height: int,
                         source: str) -> dict[str, Any] | None:
    if width <= 0 or height <= 0 or len(data) < width * height * 2:
        return None
    rgb = bytearray(width * height * 3)
    src = 0
    dst = 0
    for _ in range(width * height):
        value = data[src] | (data[src + 1] << 8)
        src += 2
        r5 = (value >> 11) & 0x1F
        g6 = (value >> 5) & 0x3F
        b5 = value & 0x1F
        rgb[dst] = (r5 << 3) | (r5 >> 2)
        rgb[dst + 1] = (g6 << 2) | (g6 >> 4)
        rgb[dst + 2] = (b5 << 3) | (b5 >> 2)
        dst += 3
    return _preview_response(bytes(rgb), width, height, source)


def _preview_from_sho(sho: bytes) -> dict[str, Any] | None:
    if len(sho) < 5:
        return None
    width = int.from_bytes(sho[0:2], "big")
    height = int.from_bytes(sho[2:4], "big")
    if width <= 0 or height <= 0 or width > SHO_MAX_WIDTH or height > SHO_MAX_HEIGHT:
        return None
    pixel_bytes = width * height * 3
    if len(sho) < 5 + pixel_bytes:
        return None
    pixels = sho[5:5 + pixel_bytes]
    rgb = bytearray(pixel_bytes)
    for index, value in enumerate(pixels):
        channel = value & 0x1F
        rgb[index] = (channel << 3) | (channel >> 2)
    return _preview_response(bytes(rgb), width, height, "Snes9X SHO")


def _preview_response(rgb: bytes, width: int, height: int,
                      source: str) -> dict[str, Any]:
    png = _encode_png_rgb(width, height, rgb)
    return {
        "source": source,
        "width": width,
        "height": height,
        "dataUrl": "data:image/png;base64,"
        + base64.b64encode(png).decode("ascii"),
    }


def _encode_png_rgb(width: int, height: int, rgb: bytes) -> bytes:
    """Encode an RGB888 buffer as a small PNG using only the stdlib."""
    if len(rgb) != width * height * 3:
        raise ValueError("RGB buffer size does not match dimensions")
    stride = width * 3
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0
        start = y * stride
        raw += rgb[start:start + stride]
    out = bytearray(b"\x89PNG\r\n\x1a\n")
    out += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    out += _png_chunk(b"IDAT", zlib.compress(bytes(raw), level=6))
    out += _png_chunk(b"IEND", b"")
    return bytes(out)


def _png_chunk(name: bytes, payload: bytes) -> bytes:
    crc = binascii.crc32(name)
    crc = binascii.crc32(payload, crc) & 0xFFFFFFFF
    return (
        len(payload).to_bytes(4, "big")
        + name
        + payload
        + crc.to_bytes(4, "big")
    )


def _base_name(filename: str) -> str:
    name = os.path.basename(filename) or "save"
    path = Path(name)
    suffix = path.suffix.lower()
    if _snes9x_explus_slot_from_name(name) is not None:
        stem = name.rsplit(".", 2)[0]
    elif _sr16_slot_from_suffix(suffix) is not None or suffix in SLOT_EXTENSIONS:
        stem = path.stem
        if (_sr16_slot_from_suffix(suffix) == 1
                and _sr16_parenthetical_slot_hint(name) is not None):
            stem = re.sub(r"\(\d{1,3}\)$", "", stem).rstrip()
    else:
        stem = name.rsplit(".", 1)[0] if "." in name else name
    return stem or "save"


def _slot_output_name(filename: str) -> str:
    slot = _sr16_output_slot(filename)
    if slot is None:
        slot = 0
    return f"{_base_name(filename)}.{slot:03d}"


def _frz_output_name(filename: str) -> str:
    slot = _sr16_output_slot(filename)
    if slot is None:
        slot = 0
    width = 2 if slot < 100 else 3
    return f"{_base_name(filename)}.{slot:0{width}d}.frz"


def _frz_from_snes9x_output_name(filename: str) -> str:
    slot = _snes9x_slot_from_name(filename)
    if slot is None:
        slot = 0
    width = 2 if slot < 100 else 3
    return f"{_base_name(filename)}.{slot:0{width}d}.frz"


def _slot_from_snes9x_output_name(filename: str) -> str:
    slot = _snes9x_slot_from_name(filename)
    if slot is None:
        slot = 0
    return f"{_base_name(filename)}.{slot:03d}"


def _sr16_output_name(filename: str) -> str:
    slot = _snes9x_slot_from_name(filename)
    if slot is None:
        slot = 1
    if slot == 0:
        slot = 1
    return f"{_base_name(filename)}.s{slot:02d}"


def _sram_output_name(filename: str) -> str:
    return _base_name(filename) + ".srm"


def _info_output_name(filename: str) -> str:
    return _base_name(filename) + ".info.json"


def _sr16_slot_from_suffix(suffix: str) -> int | None:
    if len(suffix) < 3 or not suffix.startswith(".s") or not suffix[2:].isdigit():
        return None
    value = int(suffix[2:])
    return value if 0 <= value <= 999 else None


def _sr16_output_slot(filename: str) -> int | None:
    slot = _sr16_slot_from_suffix(Path(filename).suffix.lower())
    if slot is None:
        return None
    # SR16 builds in the wild use both .s00 and .s01 as the first visible slot.
    # Preserve .s01 -> .000 unless a browser/OS-style "(N)" suffix gives a
    # clearer batch slot hint, e.g. "Game(1).s01" -> "Game.001".
    if slot == 1:
        return _sr16_parenthetical_slot_hint(filename) or 0
    return slot


def _sr16_parenthetical_slot_hint(filename: str) -> int | None:
    stem = re.sub(r"\.s\d{1,3}$", "", os.path.basename(filename), flags=re.I)
    match = re.search(r"\((\d{1,3})\)$", stem)
    if not match:
        return None
    value = int(match.group(1))
    return value if 0 <= value <= 999 else None


def _snes9x_slot_from_suffix(suffix: str) -> int | None:
    if len(suffix) != 4 or not suffix.startswith(".") or not suffix[1:].isdigit():
        return None
    return int(suffix[1:])


def _snes9x_explus_slot_from_name(filename: str) -> int | None:
    name = os.path.basename(filename).lower()
    parts = name.rsplit(".", 2)
    if len(parts) != 3 or parts[2] != "frz" or not parts[1].isdigit():
        return None
    value = int(parts[1])
    return value if 0 <= value <= 999 else None


def _snes9x_slot_from_name(filename: str) -> int | None:
    frz = _snes9x_explus_slot_from_name(filename)
    if frz is not None:
        return frz
    return _snes9x_slot_from_suffix(Path(filename).suffix.lower())
