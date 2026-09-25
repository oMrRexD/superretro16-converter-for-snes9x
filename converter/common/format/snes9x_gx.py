"""Snes9x GX (Wii/GameCube) freeze state compatibility.

Snes9x GX writes the same snapshot container and FreezeData struct tables as
desktop snes9x 1.63 (NAM/CPU/REG/PPU/DMA/VRA/RAM/SRA/FIL/CTL/TIM and the chip
chunks are byte-compatible), with two differences:

* the header says ``#!s9xsnp:0011`` (``SNAPSHOT_VERSION`` 11);
* the ``SND`` chunk is a Blargg ``snes_spc`` 0.9.0 ``copy_state`` blob
  (``SPC_SAVE_STATE_BLOCK_SIZE`` = 68 KiB + 8 = 69640 bytes) instead of the
  bsnes-derived "bapu" SMP/DSP state used by snes9x 1.63 (66560 bytes).

Desktop snes9x cannot load the GX ``SND`` layout (it treats v8-v11 snapshots
as bapu), and Snes9x GX rejects v12 snapshots.  This module translates the
APU state in both directions so every other part of the converter can keep
working on the v12 layout.  It also upgrades v8-v11 desktop bapu states
(snes9x 1.56-1.62), which share the SND size but lack the DSP
``external_regs`` block; ``load_snes9x_chunks`` handles all three variants.

snes_spc ``SND`` layout (all little-endian)::

    +0       RAM[0x10000]           real RAM (IPL ROM swapped out)
    +65536   REGS[16]               last values written by the SMP to $F0-$FF
    +65552   REGS_IN[16]            values the SMP reads ($F4-$F7 = CPU ports)
    +65568   pc u16, a, x, y, psw, sp, extra(u8 n=0)
    +65576   spc_time i16, dsp_time i16
    +65580   SPC_DSP state: identical to the bapu DSP block up to +513,
             followed by one ``extra`` byte (no external_regs copy) = 514 B
    +66094   3 x timer: next_time i16, divider u8, counter u8, extra
    +66109   extra
    +66110   reference_time i32, remainder u32
    +66118   unused (uninitialised on the Wii, zero here)

Both cores count time in SPC clocks (1.024 MHz) relative to
``spc::reference_time``, so ``spc_time`` maps to ``smp.clock`` and the
reference/remainder pair is copied as-is.  snes_spc timers are updated
lazily, so they are caught up to ``spc_time`` before being mapped onto the
bapu prescaler/divider/counter stages.
"""
from __future__ import annotations

import gzip
import struct

from converter.common.constants import (
    SNES_SND_SIZE, SND_OFF_SMP, SND_SMP_BYTES, SND_OFF_DSP, SND_DSP_BYTES,
    SND_OFF_TAIL, SND_TAIL_CPU_PORTS_REL, DSP_OFF_EXTERNAL_REGS,
)
from .snes9x import parse_snes9x, write_chunk

SNES9X_GX_VERSION = 11
SNES9X_GX_HEADER = b"#!s9xsnp:0011\n"
SNES9X_V12_HEADER = b"#!s9xsnp:0012\n"
SNES_SPC_SND_SIZE = 68 * 1024 + 8          # SPC_SAVE_STATE_BLOCK_SIZE
_GX_SRAM_SIZE = 0x80000
_BAPU_MIN_VERSION = 8                      # SNAPSHOT_VERSION_BAPU
_LEGACY_BAPU_DSP_BYTES = 514               # v8-v11 DSP block (no external_regs)

_RAM_SIZE = 0x10000
_OFF_REGS = _RAM_SIZE                      # 65536
_OFF_REGS_IN = _OFF_REGS + 16              # 65552
_OFF_CPU = _OFF_REGS_IN + 16               # 65568
_OFF_TIMES = _OFF_CPU + 8                  # 65576 (7 bytes + extra)
_OFF_DSP = _OFF_TIMES + 4                  # 65580
_SPC_DSP_BYTES = DSP_OFF_EXTERNAL_REGS + 1   # 513 shared bytes + extra = 514
_OFF_TIMERS = _OFF_DSP + _SPC_DSP_BYTES    # 66094
_TIMER_BYTES = 5
_OFF_REF = _OFF_TIMERS + 3 * _TIMER_BYTES + 1  # 66110
_SPC_BODY_END = _OFF_REF + 8               # 66118

# snes_spc SMP register indexes ($F0 + n)
_R_CONTROL = 1
_R_DSPADDR = 2
_R_CPUIO0 = 4
_R_F8 = 8
_R_F9 = 9
_R_T0TARGET = 10
_R_T0OUT = 13

_TIMER_PRESCALER = (128, 128, 16)          # SPC clocks per timer stage-1 tick
_PSW_BITS = (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01)  # n v p b h i z c

# bapu SMP::save_state field indexes (41 LE int32)
_SMP_CLOCK = 0
_SMP_OPCODE_NUMBER = 1
_SMP_OPCODE_CYCLE = 2
_SMP_PC, _SMP_SP, _SMP_A, _SMP_X, _SMP_Y = 3, 4, 5, 6, 7
_SMP_PSW_BASE = 8
_SMP_IPLROM = 16
_SMP_DSP_ADDR = 17
_SMP_F8 = 18
_SMP_F9 = 19
_SMP_TIMER_BASE = 20
_SMP_TMP_SP = 38
_SMP_TMP_YA = 39

# bapu tail after the DSP block
_TAIL_REF = 0
_TAIL_REMAINDER = 4
_TAIL_DSP_CLOCK = 8


# ---------------------------------------------------------------------------
# Container helpers
# ---------------------------------------------------------------------------

def decompress_snapshot(blob: bytes) -> bytes:
    if blob[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(blob)
        except (gzip.BadGzipFile, OSError, EOFError) as e:
            raise ValueError(f"snes9x snapshot gzip decompression failed: {e}") from e
    return blob


def snapshot_version(blob: bytes) -> int | None:
    """Return the ``#!s9xsnp:NNNN`` version of a (gzipped) snapshot."""
    plain = decompress_snapshot(blob)
    if not plain.startswith(b"#!s9xsnp:") or len(plain) < 14:
        return None
    try:
        return int(plain[9:13])
    except ValueError:
        return None


def is_snes9x_gx_chunks(chunks: dict[str, bytes]) -> bool:
    """True when the SND chunk carries a Snes9x GX snes_spc state."""
    return len(chunks.get("SND", b"")) == SNES_SPC_SND_SIZE


def build_snapshot(header: bytes, chunks: dict[str, bytes]) -> bytes:
    out = bytearray(header)
    for name, payload in chunks.items():
        out += write_chunk(name, payload)
    return bytes(out)


def normalize_snes9x_chunks(chunks: dict[str, bytes],
                            version: int | None = None) -> dict[str, bytes]:
    """Return chunks with the SND chunk in the snes9x 1.63 (v12) layout.

    * Snes9x GX snes_spc states are translated (only GX's current v11 struct
      tables are supported; older GX builds used different CPU/PPU layouts).
    * Desktop snes9x 1.56-1.62 bapu states (v8-v11) lack the 128-byte DSP
      ``external_regs`` block; they are upgraded exactly like snes9x 1.63's
      loader does.  This needs ``version``; without it v12 is assumed.

    Chunks that are already in the v12 layout are returned unchanged, so this
    is safe to call on any parsed snes9x snapshot.
    """
    if is_snes9x_gx_chunks(chunks):
        if version is not None and version != SNES9X_GX_VERSION:
            raise ValueError(
                f"Snes9x GX snapshot version {version} is not supported "
                f"(expected {SNES9X_GX_VERSION}); load and save it again in a "
                "current Snes9x GX build"
            )
        out = dict(chunks)
        out["SND"] = snes_spc_to_bapu_snd(chunks["SND"])
        return out
    if (version is not None and _BAPU_MIN_VERSION <= version < 12
            and len(chunks.get("SND", b"")) == SNES_SND_SIZE):
        out = dict(chunks)
        out["SND"] = upgrade_legacy_bapu_snd(chunks["SND"])
        return out
    return chunks


def load_snes9x_chunks(blob: bytes) -> dict[str, bytes]:
    """Parse any supported snes9x/Snes9x GX snapshot into v12-layout chunks."""
    return normalize_snes9x_chunks(parse_snes9x(blob), snapshot_version(blob))


def upgrade_legacy_bapu_snd(snd: bytes) -> bytes:
    """Upgrade a v8-v11 desktop bapu SND chunk to the v12 layout.

    Mirrors snes9x 1.63 ``S9xUnfreezeFromStream``: the 16-byte scheduler tail
    moves 128 bytes later and the DSP register file is copied into the new
    ``external_regs`` slot.
    """
    out = bytearray(snd)
    old_tail = SND_OFF_DSP + _LEGACY_BAPU_DSP_BYTES
    out[SND_OFF_TAIL:SND_OFF_TAIL + 16] = snd[old_tail:old_tail + 16]
    out[SND_OFF_DSP + DSP_OFF_EXTERNAL_REGS:SND_OFF_DSP + DSP_OFF_EXTERNAL_REGS + 128] = \
        snd[SND_OFF_DSP:SND_OFF_DSP + 128]
    out[SND_OFF_DSP + SND_DSP_BYTES - 1] = 0   # trailing extra() byte
    return bytes(out)


def snes9x_chunks_to_gx(chunks: dict[str, bytes]) -> bytes:
    """Build an uncompressed Snes9x GX (v11) snapshot from v12 chunks.

    The optional SHO screenshot is dropped: Snes9x GX stores its preview as a
    separate PNG and never writes SHO itself.
    """
    if is_snes9x_gx_chunks(chunks):
        snd = chunks["SND"]
    else:
        snd = bapu_to_snes_spc_snd(chunks["SND"])
    out: dict[str, bytes] = {}
    for name, payload in chunks.items():
        if name == "SHO":
            continue
        if name == "SND":
            payload = snd
        elif name == "SRA" and len(payload) < _GX_SRAM_SIZE:
            # GX always writes 512 KiB and rejects a zero-length block.
            payload = payload + bytes(_GX_SRAM_SIZE - len(payload))
        out[name] = payload
    return build_snapshot(SNES9X_GX_HEADER, out)


def gx_chunks_to_snes9x(chunks: dict[str, bytes]) -> bytes:
    """Build an uncompressed desktop snes9x (v12) snapshot from GX chunks."""
    return build_snapshot(SNES9X_V12_HEADER, normalize_snes9x_chunks(chunks))


# ---------------------------------------------------------------------------
# snes_spc -> bapu
# ---------------------------------------------------------------------------

def _catch_up_timer(next_time: int, divider: int, counter: int, *,
                    time: int, prescaler: int, period: int,
                    enabled: bool) -> tuple[int, int, int]:
    """Replay snes_spc ``run_timer_`` so the timer is current at ``time``."""
    if time < next_time:
        return next_time, divider, counter
    elapsed = (time - next_time) // prescaler + 1
    next_time += elapsed * prescaler
    if enabled:
        remain = ((period - divider - 1) & 0xFF) + 1
        divider += elapsed
        over = elapsed - remain
        if over >= 0:
            n = over // period
            counter = (counter + 1 + n) & 0x0F
            divider = over - n * period
    return next_time, divider & 0xFF, counter


def snes_spc_to_bapu_snd(old: bytes) -> bytes:
    """Translate a Snes9x GX ``SND`` chunk into the snes9x 1.63 layout."""
    if len(old) < _SPC_BODY_END:
        raise ValueError(
            f"Snes9x GX SND chunk too short: {len(old)} bytes, "
            f"expected {SNES_SPC_SND_SIZE}"
        )
    regs = old[_OFF_REGS:_OFF_REGS + 16]
    regs_in = old[_OFF_REGS_IN:_OFF_REGS_IN + 16]
    pc = int.from_bytes(old[_OFF_CPU:_OFF_CPU + 2], "little")
    spc_a, spc_x, spc_y, psw, sp = old[_OFF_CPU + 2:_OFF_CPU + 7]
    spc_time, dsp_time = struct.unpack_from("<hh", old, _OFF_TIMES)
    for off in (_OFF_CPU + 7, _OFF_DSP + _SPC_DSP_BYTES - 1, _OFF_REF - 1):
        if old[off] != 0:
            raise ValueError(
                "unsupported Snes9x GX SND chunk: unexpected snes_spc extra "
                f"block at offset {off}"
            )

    ram = bytearray(old[:_RAM_SIZE])
    # CPU-readable ports live in apuram[$F4-$F7] on bapu.
    ram[0xF4:0xF8] = regs[_R_CPUIO0:_R_CPUIO0 + 4]

    control = regs[_R_CONTROL]
    smp = [0] * (SND_SMP_BYTES // 4)
    smp[_SMP_CLOCK] = spc_time
    smp[_SMP_PC] = pc
    smp[_SMP_SP] = sp
    smp[_SMP_A] = spc_a
    smp[_SMP_X] = spc_x
    smp[_SMP_Y] = spc_y
    for i, bit in enumerate(_PSW_BITS):
        smp[_SMP_PSW_BASE + i] = 1 if psw & bit else 0
    smp[_SMP_IPLROM] = control & 0x80
    smp[_SMP_DSP_ADDR] = regs[_R_DSPADDR]
    smp[_SMP_F8] = regs_in[_R_F8]
    smp[_SMP_F9] = regs_in[_R_F9]
    for i in range(3):
        base = _OFF_TIMERS + i * _TIMER_BYTES
        next_time, divider, counter, extra = struct.unpack_from("<hBBB", old, base)
        if extra != 0:
            raise ValueError(
                "unsupported Snes9x GX SND chunk: unexpected timer extra block"
            )
        prescaler = _TIMER_PRESCALER[i]
        period = ((regs[_R_T0TARGET + i] - 1) & 0xFF) + 1
        enabled = bool(control >> i & 1)
        next_time, divider, counter = _catch_up_timer(
            next_time, divider, counter, time=spc_time,
            prescaler=prescaler, period=period, enabled=enabled,
        )
        stage1 = prescaler - (next_time - spc_time)
        stage1 = max(0, min(prescaler - 1, stage1))
        t = _SMP_TIMER_BASE + i * 5
        smp[t] = 1 if enabled else 0
        smp[t + 1] = period
        smp[t + 2] = stage1
        smp[t + 3] = divider
        smp[t + 4] = counter & 0x0F
    smp[_SMP_TMP_SP] = sp
    smp[_SMP_TMP_YA] = (spc_y << 8) | spc_a

    dsp = bytearray(SND_DSP_BYTES)
    dsp[:DSP_OFF_EXTERNAL_REGS] = old[_OFF_DSP:_OFF_DSP + DSP_OFF_EXTERNAL_REGS]
    dsp[DSP_OFF_EXTERNAL_REGS:DSP_OFF_EXTERNAL_REGS + 128] = old[_OFF_DSP:_OFF_DSP + 128]

    tail = bytearray(SNES_SND_SIZE - SND_OFF_TAIL)
    reference_time, remainder = struct.unpack_from("<iI", old, _OFF_REF)
    struct.pack_into("<i", tail, _TAIL_REF, reference_time)
    struct.pack_into("<I", tail, _TAIL_REMAINDER, remainder)
    # bapu counts DSP clocks still owed; snes_spc may have run the DSP ahead.
    struct.pack_into("<i", tail, _TAIL_DSP_CLOCK, max(0, spc_time - dsp_time))
    tail[SND_TAIL_CPU_PORTS_REL:SND_TAIL_CPU_PORTS_REL + 4] = \
        regs_in[_R_CPUIO0:_R_CPUIO0 + 4]

    out = bytes(ram) + struct.pack(f"<{len(smp)}i", *smp) + bytes(dsp) + bytes(tail)
    assert len(out) == SNES_SND_SIZE
    return out


# ---------------------------------------------------------------------------
# bapu -> snes_spc
# ---------------------------------------------------------------------------

def bapu_to_snes_spc_snd(snd: bytes) -> bytes:
    """Translate a snes9x 1.63 ``SND`` chunk into the Snes9x GX layout."""
    if len(snd) < SND_OFF_TAIL + 16:
        raise ValueError(
            f"snes9x SND chunk too short: {len(snd)} bytes, expected {SNES_SND_SIZE}"
        )
    smp = struct.unpack_from(f"<{SND_SMP_BYTES // 4}i", snd, SND_OFF_SMP)
    dsp = snd[SND_OFF_DSP:SND_OFF_DSP + SND_DSP_BYTES]
    reference_time, remainder, dsp_clock = struct.unpack_from("<iIi", snd, SND_OFF_TAIL)
    cpu_ports = snd[SND_OFF_TAIL + SND_TAIL_CPU_PORTS_REL:
                    SND_OFF_TAIL + SND_TAIL_CPU_PORTS_REL + 4]
    ram = bytearray(snd[:_RAM_SIZE])

    control = (0x80 if smp[_SMP_IPLROM] else 0)
    for i in range(3):
        if smp[_SMP_TIMER_BASE + i * 5]:
            control |= 1 << i

    # REGS mirrors what the SMP last wrote to $F0-$FF (snes_spc keeps the same
    # bytes in RAM); take the unsaved ones from RAM and the rest from state.
    regs = bytearray(ram[0xF0:0x100])
    regs[_R_CONTROL] = (regs[_R_CONTROL] & 0x30) | control
    regs[_R_DSPADDR] = smp[_SMP_DSP_ADDR] & 0xFF
    regs[_R_CPUIO0:_R_CPUIO0 + 4] = ram[0xF4:0xF8]
    for i in range(3):
        regs[_R_T0TARGET + i] = smp[_SMP_TIMER_BASE + i * 5 + 1] & 0xFF
    ram[0xF0:0x100] = regs

    regs_in = bytearray(16)
    regs_in[_R_CPUIO0:_R_CPUIO0 + 4] = cpu_ports
    regs_in[_R_F8] = smp[_SMP_F8] & 0xFF
    regs_in[_R_F9] = smp[_SMP_F9] & 0xFF
    for i in range(3):
        regs_in[_R_T0OUT + i] = smp[_SMP_TIMER_BASE + i * 5 + 4] & 0x0F

    psw = 0
    for i, bit in enumerate(_PSW_BITS):
        if smp[_SMP_PSW_BASE + i]:
            psw |= bit

    spc_time = max(-0x8000, min(0x7FFF, smp[_SMP_CLOCK]))
    dsp_time = max(-0x8000, min(0x7FFF, spc_time - dsp_clock))

    out = bytearray(SNES_SPC_SND_SIZE)
    out[:_RAM_SIZE] = ram
    out[_OFF_REGS:_OFF_REGS + 16] = regs
    out[_OFF_REGS_IN:_OFF_REGS_IN + 16] = regs_in
    struct.pack_into("<H5B", out, _OFF_CPU, smp[_SMP_PC] & 0xFFFF,
                     smp[_SMP_A] & 0xFF, smp[_SMP_X] & 0xFF, smp[_SMP_Y] & 0xFF,
                     psw, smp[_SMP_SP] & 0xFF)
    struct.pack_into("<hh", out, _OFF_TIMES, spc_time, dsp_time)
    out[_OFF_DSP:_OFF_DSP + DSP_OFF_EXTERNAL_REGS] = dsp[:DSP_OFF_EXTERNAL_REGS]
    for i in range(3):
        t = _SMP_TIMER_BASE + i * 5
        prescaler = _TIMER_PRESCALER[i]
        stage1 = max(0, min(prescaler - 1, smp[t + 2]))
        next_time = max(-0x8000, min(0x7FFF, spc_time + prescaler - stage1))
        struct.pack_into("<hBB", out, _OFF_TIMERS + i * _TIMER_BYTES,
                         next_time, smp[t + 3] & 0xFF, smp[t + 4] & 0x0F)
    struct.pack_into("<iI", out, _OFF_REF, reference_time, remainder & 0xFFFFFFFF)
    return bytes(out)
