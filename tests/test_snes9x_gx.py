"""Snes9x GX (Wii/GameCube) snes_spc <-> snes9x 1.63 bapu translation."""
from __future__ import annotations

import gzip
import struct
from pathlib import Path

import pytest

from converter.cli import main as converter_main
from converter.common.constants import SNES_SND_SIZE, SND_OFF_SMP, SND_OFF_TAIL
from converter.common.format.snes9x import SNES9X_HEADER, parse_snes9x, write_chunk
from converter.common.format import snes9x_gx as gx

ROOT = Path(__file__).resolve().parents[1]
WII_SAVE = ROOT / "do wii Chrono Trigger (USA) 3.frz"
GX_HEADER = gx.SNES9X_GX_HEADER


def _spc_state(*, spc_time=-1, dsp_time=0, timers=((22, 37, 0), (22, 44, 3), (6, 0, 15)),
               control=0x03, targets=(0x2A, 0x80, 0x00)) -> bytes:
    snd = bytearray(gx.SNES_SPC_SND_SIZE)
    for i in range(0x10000):
        snd[i] = (i * 7) & 0xFF
    regs = bytearray(16)
    regs[0] = 0x0A
    regs[1] = control
    regs[2] = 0x4C
    regs[4:8] = b"\x11\x22\x33\x44"
    regs[10:13] = bytes(targets)
    snd[0xF0:0x100] = regs
    snd[65536:65552] = regs
    regs_in = bytearray(16)
    regs_in[4:8] = b"\xAA\xBB\xCC\xDD"
    regs_in[8] = 0x5A
    regs_in[9] = 0xA5
    snd[65552:65568] = regs_in
    struct.pack_into("<H5BB", snd, 65568, 0x029C, 0x1F, 0x02, 0x03, 0xA3, 0xEF, 0)
    struct.pack_into("<hh", snd, 65576, spc_time, dsp_time)
    for i in range(513):
        snd[65580 + i] = (i * 13 + 1) & 0xFF
    snd[65580 + 513] = 0
    for i, (next_time, divider, counter) in enumerate(timers):
        struct.pack_into("<hBBB", snd, 66094 + i * 5, next_time, divider, counter, 0)
    snd[66109] = 0
    struct.pack_into("<iI", snd, 66110, 2, 134884)
    return bytes(snd)


def _snapshot(header: bytes, snd: bytes, *, sra: bytes = b"\x00" * 0x2000,
              sho: bool = False) -> bytes:
    plain = bytearray(header)
    plain += write_chunk("NAM", b"Game\x00")
    plain += write_chunk("SRA", sra)
    plain += write_chunk("SND", snd)
    if sho:
        plain += write_chunk("SHO", b"\x01" * 16)
    return gzip.compress(bytes(plain), mtime=0)


class TestSndTranslation:
    def test_spc_to_bapu_layout(self):
        bapu = gx.snes_spc_to_bapu_snd(_spc_state())
        assert len(bapu) == SNES_SND_SIZE
        smp = struct.unpack_from("<41i", bapu, SND_OFF_SMP)
        assert smp[0] == -1                     # spc_time -> smp.clock
        assert smp[3:8] == (0x029C, 0xEF, 0x1F, 0x02, 0x03)
        assert smp[8:16] == (1, 0, 1, 0, 0, 0, 1, 1)   # psw 0xA3
        assert smp[16:20] == (0, 0x4C, 0x5A, 0xA5)
        # timer0: enabled, target 42, next tick in 23 clocks -> stage1 105
        assert smp[20:25] == (1, 42, 105, 37, 0)
        assert smp[25:30] == (1, 128, 105, 44, 3)
        # timer2 disabled, target 0 -> 256
        assert smp[30:35] == (0, 256, 9, 0, 15)
        assert bapu[0xF4:0xF8] == b"\x11\x22\x33\x44"
        ref, rem, dsp_clock = struct.unpack_from("<iIi", bapu, SND_OFF_TAIL)
        assert (ref, rem, dsp_clock) == (2, 134884, 0)
        assert bapu[SND_OFF_TAIL + 12:SND_OFF_TAIL + 16] == b"\xAA\xBB\xCC\xDD"
        dsp = bapu[65700:65700 + 642]
        assert dsp[:513] == _spc_state()[65580:65580 + 513]
        assert dsp[513:641] == dsp[:128]        # external_regs mirror

    def test_roundtrip_preserves_emulated_state(self):
        old = _spc_state(spc_time=3, dsp_time=0)
        back = gx.bapu_to_snes_spc_snd(gx.snes_spc_to_bapu_snd(old))
        assert len(back) == gx.SNES_SPC_SND_SIZE
        assert back[:0x10000] == old[:0x10000]
        assert back[65536:65552] == old[65536:65552]            # REGS
        assert back[65552:65562] == old[65552:65562]            # REGS_IN ports/f8/f9
        assert back[65568:65580] == old[65568:65580]            # CPU regs + times
        assert back[65580:66110] == old[65580:66110]            # DSP + timers
        assert back[66110:66118] == old[66110:66118]            # reference/remainder

    def test_lazy_timer_is_caught_up(self):
        # timer0 last updated long ago: 3 prescaler ticks are owed.
        old = _spc_state(spc_time=300, timers=((-80, 40, 1), (400, 0, 0), (400, 0, 0)))
        smp = struct.unpack_from("<41i", gx.snes_spc_to_bapu_snd(old), SND_OFF_SMP)
        # elapsed = (300+80)//128+1 = 3 -> divider 40+3 wraps at 42 -> counter 2
        assert smp[20:25] == (1, 42, 128 - (304 - 300), 1, 2)

    def test_rejects_unknown_extra_blocks(self):
        bad = bytearray(_spc_state())
        bad[65575] = 4
        with pytest.raises(ValueError, match="extra"):
            gx.snes_spc_to_bapu_snd(bytes(bad))


class TestContainer:
    def test_detection_and_version(self):
        blob = _snapshot(b"#!s9xsnp:0011\n", _spc_state())
        assert gx.snapshot_version(blob) == 11
        assert gx.is_snes9x_gx_chunks(parse_snes9x(blob))
        assert not gx.is_snes9x_gx_chunks({"SND": bytes(SNES_SND_SIZE)})

    def test_v12_to_gx_drops_sho_and_pads_sram(self):
        bapu = gx.snes_spc_to_bapu_snd(_spc_state())
        chunks = parse_snes9x(_snapshot(SNES9X_HEADER, bapu, sra=b"", sho=True))
        plain = gx.snes9x_chunks_to_gx(chunks)
        assert plain.startswith(b"#!s9xsnp:0011\n")
        out = parse_snes9x(plain)
        assert list(out) == ["NAM", "SRA", "SND"]
        assert len(out["SRA"]) == 0x80000
        assert len(out["SND"]) == gx.SNES_SPC_SND_SIZE

    def test_gx_to_v12(self):
        plain = gx.gx_chunks_to_snes9x(parse_snes9x(_snapshot(b"#!s9xsnp:0011\n", _spc_state())))
        assert plain.startswith(b"#!s9xsnp:0012\n")
        assert len(parse_snes9x(plain)["SND"]) == SNES_SND_SIZE

    def test_normalize_leaves_desktop_chunks_alone(self):
        chunks = {"SND": bytes(SNES_SND_SIZE)}
        assert gx.normalize_snes9x_chunks(chunks) is chunks


class TestVersionAwareLoading:
    def test_legacy_bapu_v11_is_upgraded(self):
        snd = bytearray(SNES_SND_SIZE)
        snd[65700:65700 + 128] = bytes(range(128))           # DSP regs
        snd[65700 + 513] = 0                                  # old extra()
        tail = struct.pack("<iIi4B", 7, 99, 3, 1, 2, 3, 4)
        snd[65700 + 514:65700 + 514 + 16] = tail
        chunks = gx.load_snes9x_chunks(_snapshot(GX_HEADER, bytes(snd)))
        new = chunks["SND"]
        assert new[SND_OFF_TAIL:SND_OFF_TAIL + 16] == tail
        assert new[65700 + 513:65700 + 641] == bytes(range(128))
        assert new[65700 + 641] == 0

    def test_v12_bapu_is_untouched(self):
        snd = bytes(range(256)) * (SNES_SND_SIZE // 256)
        chunks = gx.load_snes9x_chunks(_snapshot(SNES9X_HEADER, snd))
        assert chunks["SND"] == snd

    def test_old_gx_version_is_rejected(self):
        with pytest.raises(ValueError, match="Snes9x GX snapshot version 10"):
            gx.load_snes9x_chunks(_snapshot(b"#!s9xsnp:0010" + b"\n", _spc_state()))


class TestCli:
    def test_gx_roundtrip_commands(self, tmp_path):
        src = tmp_path / "Game 3.frz"
        src.write_bytes(_snapshot(b"#!s9xsnp:0011\n", _spc_state()))
        desk = tmp_path / "Game.003"
        back = tmp_path / "Game 4.frz"
        converter_main(["gx-to-snes9x", str(src), str(desk)])
        converter_main(["snes9x-to-gx", str(desk), str(back)])
        assert gx.snapshot_version(desk.read_bytes()) == 12
        assert gx.snapshot_version(back.read_bytes()) == 11
        with pytest.raises(SystemExit):
            converter_main(["gx-to-snes9x", str(desk), str(tmp_path / "x.000")])

    @pytest.mark.parametrize("name,expected", [
        ("Game 1.frz", True), ("Game Auto.frz", True), ("Game.frz", True),
        ("Game.00.frz", False), ("Game.000", False),
    ])
    def test_gx_output_name_detection(self, name, expected):
        from converter.cli import _is_snes9x_gx_output_path
        assert _is_snes9x_gx_output_path(name) is expected


@pytest.mark.skipif(not WII_SAVE.exists(), reason="local Wii calibration save absent")
def test_real_wii_save_roundtrip():
    chunks = parse_snes9x(WII_SAVE.read_bytes())
    assert gx.is_snes9x_gx_chunks(chunks)
    old = chunks["SND"]
    back = gx.bapu_to_snes_spc_snd(gx.snes_spc_to_bapu_snd(old))
    assert back[:0x10000] == old[:0x10000]
    assert back[65580:65580 + 513] == old[65580:65580 + 513]
    assert back[66110:66118] == old[66110:66118]
