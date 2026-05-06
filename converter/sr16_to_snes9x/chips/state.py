"""SR16 special-chip section translators (SA1, SuperFX, DSP-1/2/4, Cx4, BSX, ...).

These are emitted as snes9x optional chip chunks (SFX, SA1/SAR, DP1/DP2/DP4,
CX4, BSX, SRT/CLK, OBC/OBM, ST0). Without them, snes9x rejects snapshots for
chip-using games with a misleading "ROM not found" error.
"""
from __future__ import annotations
from urllib.parse import unquote

from converter.common.constants import (
    SR16_PSD_SIZE, SR16_SAX_SIZE, SR16_SA1_SIZE, SR16_4XC_SIZE,
    SNES_DP4_SIZE, SNES_SFX_SIZE, SNES_SA1_SIZE, SNES_REG_SIZE,
    SR16_REG_OFF_DB, SR16_REG_OFF_P, SR16_REG_OFF_A, SR16_REG_OFF_D,
    SR16_REG_OFF_S, SR16_REG_OFF_X, SR16_REG_OFF_Y, SR16_REG_OFF_PC_FULL,
)
from converter.common.format.sr16 import SR16Save
from ..game_registry import chip_stubs_for_source


def _reg_from_sr16_register_prefix(data: bytes) -> bytes:
    """Extract a snes9x REG/SAR register chunk from an SR16 register prefix."""
    if len(data) < 0x1D:
        return b"\x00" * SNES_REG_SIZE

    def rb(off: int, size: int) -> int:
        return int.from_bytes(data[off:off + size], "big")

    db = rb(SR16_REG_OFF_DB, 1)
    p = rb(SR16_REG_OFF_P, 4) & 0xFFFF
    a = rb(SR16_REG_OFF_A, 4) & 0xFFFF
    d = rb(SR16_REG_OFF_D, 4) & 0xFFFF
    s = rb(SR16_REG_OFF_S, 4) & 0xFFFF
    x = rb(SR16_REG_OFF_X, 4) & 0xFFFF
    y = rb(SR16_REG_OFF_Y, 4) & 0xFFFF
    pc_full = rb(SR16_REG_OFF_PC_FULL, 4)
    pb = (pc_full >> 16) & 0xFF
    pc = pc_full & 0xFFFF

    out = bytearray(SNES_REG_SIZE)
    out[0] = pb
    out[1] = db
    out[2:4] = p.to_bytes(2, "big")
    out[4:6] = a.to_bytes(2, "big")
    out[6:8] = d.to_bytes(2, "big")
    out[8:10] = s.to_bytes(2, "big")
    out[10:12] = x.to_bytes(2, "big")
    out[12:14] = y.to_bytes(2, "big")
    out[14:16] = pc.to_bytes(2, "big")
    return bytes(out)


def _build_sa1_chunks_from_sr16(sr16: SR16Save) -> list[tuple[str, bytes]]:
    """Translate SR16's old SA1 section to snes9x SA1/SAR chunks."""
    sa1 = sr16.by_code("SA1")
    if sa1 is None or len(sa1.data) != SR16_SA1_SIZE:
        return []

    sar = _reg_from_sr16_register_prefix(sa1.data)
    pb, db = sar[0], sar[1]
    f01 = sr16.by_code("F01")
    fill = f01.data if f01 else b""

    def fill_u16(addr: int) -> int:
        if len(fill) > addr + 1:
            return fill[addr] | (fill[addr + 1] << 8)
        return 0

    out = bytearray()
    out += (pb << 16).to_bytes(4, "big")       # ShiftedPB
    out += (db << 16).to_bytes(4, "big")       # ShiftedDB
    out += (0).to_bytes(4, "big")              # Flags
    out.append(0)                              # WaitingForInterrupt
    out.append(1 if (sar[2] & 0x40) else 0)    # overflow
    out.append(0)                              # in_char_dma
    out += (0).to_bytes(2, "big")              # op1
    out += (0).to_bytes(2, "big")              # op2
    out += (0).to_bytes(4, "big")              # arithmetic_op
    out += (0).to_bytes(8, "big")              # sum
    out.append(2 if (len(fill) > 0x223F and fill[0x223F] & 0x80) else 4)
    out.append(0)                              # variable_bit_pos
    out += (0).to_bytes(4, "big")              # Cycles
    out += (0).to_bytes(4, "big")              # PrevCycles
    out.append(0)                              # TimerIRQLastState
    out += fill_u16(0x2212).to_bytes(2, "big") # HTimerIRQPos
    out += fill_u16(0x2214).to_bytes(2, "big") # VTimerIRQPos
    out += (0).to_bytes(2, "big")              # HCounter
    out += (0).to_bytes(2, "big")              # VCounter
    out += (0).to_bytes(2, "big")              # PrevHCounter
    out += (6).to_bytes(4, "big")              # MemSpeed
    out += (12).to_bytes(4, "big")             # MemSpeedx2
    assert len(out) == SNES_SA1_SIZE
    return [("SA1", bytes(out)), ("SAR", sar)]


def _build_sfx_chunk_from_sax(sax: bytes) -> bytes | None:
    """Expand SR16's compact old SuperFX payload to snes9x's SFX chunk."""
    if len(sax) < SR16_SAX_SIZE:
        return None

    words = [int.from_bytes(sax[i:i + 2], "big") for i in range(0, 70, 2)]
    regs = words[:16]
    tail = words[16:]

    out = bytearray()
    for value in regs:
        out += value.to_bytes(4, "big")

    def put_u32(value: int) -> None:
        out.extend((value & 0xFFFFFFFF).to_bytes(4, "big"))

    def put_u8(value: int) -> None:
        out.append(value & 0xFF)

    # The compact SR16 SAX chunk stores the live 16-bit GSU registers first.
    # Remaining SuperFX emulator internals are either absent or in an older
    # order, so seed conservative values and let the game rewrite registers.
    put_u32(tail[13] if len(tail) > 13 else 0)   # vColorReg
    put_u32(0)                                   # vPlotOptionReg
    put_u32(tail[2] if len(tail) > 2 else 0)     # vStatusReg
    put_u32(tail[15] & 0xFF if len(tail) > 15 else 0) # vPrgBankReg
    put_u32(0)                                   # vRomBankReg
    put_u32(0)                                   # vRamBankReg
    put_u32(0)                                   # vCacheBaseReg
    put_u32(0)                                   # vCacheFlags
    put_u32(0)                                   # vLastRamAdr
    put_u32(0)                                   # pvDreg relative to avReg
    put_u32(0)                                   # pvSreg relative to avReg
    put_u8(0)                                    # vRomBuffer
    put_u8(0)                                    # vPipe
    put_u32(0)                                   # vPipeAdr
    put_u32(regs[15] & 0x8000)                   # vSign
    put_u32(0 if regs[15] else 1)                # vZero
    put_u32(1 if tail and tail[0] & 1 else 0)    # vCarry
    put_u32(0)                                   # vOverflow
    put_u32(0)                                   # vErrorCode
    put_u32(0)                                   # vIllegalAddress
    put_u8(0)                                    # bBreakPoint
    put_u32(0)                                   # vBreakPoint
    put_u32(0)                                   # vStepPoint
    put_u32(2)                                   # nRamBanks
    put_u32(64)                                  # nRomBanks
    put_u32(0)                                   # vMode
    put_u32(0xFFFFFFFF)                          # vPrevMode
    put_u32(0)                                   # pvScreenBase relative to pvRam
    for _ in range(32):
        put_u32(0)                               # apvScreen[N] relative to pvRam
    for _ in range(32):
        put_u32(0)                               # x[N]
    put_u32(0)                                   # vScreenHeight
    put_u32(0)                                   # vScreenRealHeight
    put_u32(0xFFFFFFFF)                          # vPrevScreenHeight
    put_u32(0)                                   # vScreenSize
    put_u32(0)                                   # pvRamBank relative to apvRamBank
    put_u32(0)                                   # pvRomBank relative to apvRomBank
    put_u32(0)                                   # pvPrgBank relative to apvRomBank
    for _ in range(4):
        put_u32(0)                               # apvRamBank[N] relative to pvRam
    put_u8(0)                                    # bCacheActive
    put_u32(0)                                   # pvCache relative to pvRegisters
    out += b"\x00" * 512                         # avCacheBackup
    put_u32(0)                                   # vCounter
    put_u32(0)                                   # vInstCount
    put_u32(1)                                   # vSCBRDirty
    assert len(out) == SNES_SFX_SIZE
    return bytes(out)


def _source_title(sr16: SR16Save) -> str:
    return unquote(sr16.source_name).lower()


def _dsp_chunk_name_for_sr16_psd(sr16: SR16Save) -> str:
    """Choose one snes9x DSP-family chunk for SR16's generic PSD payload.

    This is intentionally payload-driven, not title-driven. Emitting every DSP
    chunk looked attractive, but snes9x 1.63 can crash after loading snapshots
    that contain unrelated optional chip chunks. SR16's DSP-4 saves observed so
    far start with a distinctive version/protocol header (`03 01 01`) and keep
    the opaque transient block empty; everything else uses the safer
    DSP-1-compatible payload.
    """
    psd = sr16.by_code("PSD")
    if psd is not None and _looks_like_sr16_dp4_psd(psd.data):
        return "DP4"
    return "DP1"


def _looks_like_sr16_dp4_psd(data: bytes) -> bool:
    """Return True for SR16's observed DSP-4 PSD shape.

    Top Gear 3000 saves a `PSD:1450` block whose header starts
    `03 01 01 ...` and whose opaque transient block is zero. Idle captures have
    zeroed protocol buffers; this predicate also allows valid pending
    parameter/output counters so `_dp4_payload_from_sr16_psd()` can preserve a
    future in-flight DSP-4 transaction instead of falling back to DP1.
    """
    if len(data) != SR16_PSD_SIZE or data[:3] != b"\x03\x01\x01":
        return False
    in_count = int.from_bytes(data[0x04:0x08], "big")
    in_index = int.from_bytes(data[0x08:0x0C], "big")
    out_count = int.from_bytes(data[0x0C:0x10], "big")
    out_index = int.from_bytes(data[0x10:0x14], "big")
    temp_save_data = data[0x414:0x414 + 406]
    return (
        0 <= in_index <= in_count <= 512
        and 0 <= out_index <= out_count <= 512
        and not any(temp_save_data)
    )


def _dsp_payload_from_sr16_psd(name: str, data: bytes) -> bytes:
    """Convert SR16's PSD payload to the chosen snes9x DSP-family chunk."""
    return _dsp_payload_from_sr16_psd_for_state(name, data, None)


def _dsp_payload_from_sr16_psd_for_state(name: str, data: bytes,
                                         sr16: SR16Save | None) -> bytes:
    """Convert SR16's PSD payload with optional CPU-context hints."""
    if len(data) == SR16_PSD_SIZE:
        if name == "DP1":
            # SR16 carries one leading selector byte before the DSP-1 snapshot.
            return data[1:]
        if name == "DP4":
            return _dp4_payload_from_sr16_psd(
                data,
                force_idle_drain=(
                    sr16 is not None and _cpu_looks_inside_dp4_io_routine(sr16)
                ),
            )
    return data


def _cpu_looks_inside_dp4_io_routine(sr16: SR16Save) -> bool:
    """Return True when SR16 captured the CPU inside a DSP-4 I/O routine.

    SR16's idle DSP-4 PSD does not say whether the CPU is currently in the
    middle of a command/readback transaction. Top Gear 3000 exposed both
    cases: one save needs a fake zero-output drain to escape a `$8000` polling
    loop, while another is outside that loop and freezes if new commands are
    swallowed. The only reliable evidence available without the ROM is the
    saved CPU execution point. This guard intentionally checks the recovered
    DSP-4 service-code range, not the state filename.
    """
    c01 = sr16.by_code("C01")
    if c01 is None or len(c01.data) < SR16_REG_OFF_PC_FULL + 4:
        return False
    pc_full = int.from_bytes(
        c01.data[SR16_REG_OFF_PC_FULL:SR16_REG_OFF_PC_FULL + 4], "big"
    )
    pb = (pc_full >> 16) & 0xFF
    pc = pc_full & 0xFFFF
    db = c01.data[SR16_REG_OFF_DB]
    return db == 0x30 and pb == 0x82 and 0xD000 <= pc <= 0xDFFF


# SR16 PSD layout: a DSP-1-style header shared across DSP-1/2/4.
# Total 1450 bytes in observed saves.
#   +0x000  version          1B   (selector / format byte; 0x03 in tested saves)
#   +0x001  waiting4command  1B   bool8
#   +0x002  first_parameter  1B   bool8 (DSP-1 protocol; not used by DSP-4)
#   +0x003  command          1B   uint8 (DSP-4 16-bit cmd low byte; high in temp)
#   +0x004  in_count         4B   uint32 BE
#   +0x008  in_index         4B   uint32 BE
#   +0x00C  out_count        4B   uint32 BE
#   +0x010  out_index        4B   uint32 BE
#   +0x014  parameters       512B
#   +0x214  output           512B
#   +0x414  temp_save_data   406B (DSP-4 extra state; opaque, often empty)
def _dp4_payload_from_sr16_psd(psd: bytes,
                               force_idle_drain: bool = False) -> bytes:
    """Translate SR16 PSD (1450B) to snes9x SDSP4 (1297B, BE struct).

    SR16 stores DSP-1/2/4 with a single DSP-1-shaped header (waiting4command,
    first_parameter, command8, in_count/index, out_count/index, parameters[512],
    output[512], temp_save_data[406]). DSP-4-specific runtime state (Logic,
    world_*, viewport_*, poly_*, OAM_*) is NOT exposed by SR16's secondary
    FreezeData table — it would have to live opaquely inside temp_save_data,
    and tested DSP-4 saves leave temp_save_data entirely zero, suggesting SR16
    does not actually serialize DSP-4 transient state at all (PSD acts as a
    placeholder with only the version byte set).

    Translation rules:
      - Output queue holds pending bytes (out_index < out_count <= 512):
          carry parameters/output/counts forward and set waiting4command=TRUE.
          The CPU's read loop drains the buffer, then re-issues its next
          command, which DSP4SetByte handles correctly from the reset baseline.
      - Idle SR16 DSP (waiting4command=TRUE, all counts 0):
          normally emit snes9x's reset DP4. Only emit the fake drain buffer
          when CPU context shows the save was captured inside a DSP-4 I/O
          routine. Draining outside that routine swallows the next real command
          and can freeze road projection.
    """
    if len(psd) != SR16_PSD_SIZE:
        return _default_dp4_chunk()

    waiting   = psd[1]
    in_count  = int.from_bytes(psd[0x04:0x08], "big")
    in_index  = int.from_bytes(psd[0x08:0x0C], "big")
    out_count = int.from_bytes(psd[0x0C:0x10], "big")
    out_index = int.from_bytes(psd[0x10:0x14], "big")

    drain_pending = (waiting != 0
                     and in_count == 0 and in_index == 0
                     and 0 < out_index < out_count <= 512)
    if drain_pending:
        out = bytearray(_default_dp4_chunk())
        # SDSP4: waiting4command(1), half_command(1), command(2), in_count(4),
        #        in_index(4), out_count(4), out_index(4), parameters(512),
        #        output(512), byte(1), address(2), ...
        # All ints are big-endian.
        out[0]      = 1                                    # waiting4command
        out[1]      = 0                                    # half_command
        out[2:4]    = (psd[3]).to_bytes(2, "big")          # command (8b -> 16b)
        out[4:8]    = (in_count).to_bytes(4, "big")
        out[8:12]   = (in_index).to_bytes(4, "big")
        out[12:16]  = (out_count).to_bytes(4, "big")
        out[16:20]  = (out_index).to_bytes(4, "big")
        out[0x14:0x214]  = psd[0x14:0x214]                 # parameters[512]
        out[0x214:0x414] = psd[0x214:0x414]                # output[512]
        return bytes(out)

    if force_idle_drain:
        return _drain_dp4_chunk()

    return _default_dp4_chunk()


def _default_dp4_chunk() -> bytes:
    """Return snes9x's reset SDSP4 state as a serialized DP4 chunk.

    Layout matches snes9x SnapDSP4 (snapshot.cpp). Total = 1297 bytes BE.
    Only field set is waiting4command = TRUE; everything else is zero,
    matching `memset(&DSP4, 0, sizeof(DSP4)); DSP4.waiting4command = TRUE;`
    in S9xResetDSP().
    """
    out = bytearray(SNES_DP4_SIZE)
    out[0] = 1  # DSP4.waiting4command = TRUE
    return bytes(out)


def _drain_dp4_chunk() -> bytes:
    """Return a DP4 chunk that absorbs in-flight DSP-4 traffic.

    out_count=512, out_index=0, output[]=zeros. DSP4_SetByte sees
    out_index<out_count and just increments out_index for any CPU write.
    DSP4_GetByte returns output[out_index]=0 for any read, then increments.
    After 512 byte ops, out_count is cleared while waiting4command is still
    true, so DSP-4 re-enters command-decode on the next write.
    See _dp4_payload_from_sr16_psd for why this is needed.
    """
    out = bytearray(SNES_DP4_SIZE)
    out[0] = 1
    # waiting4command(1)=1  half_command(1)=0  command(2)=0
    # in_count(4)=0  in_index(4)=0  out_count(4)=512  out_index(4)=0
    out[12:16] = (512).to_bytes(4, "big")
    # parameters[0x14..0x214]=0  output[0x214..0x414]=0  (already zero)
    return bytes(out)


def _compatibility_stub_chip_chunks(sr16: SR16Save) -> list[tuple[str, bytes]]:
    """Return minimal chunks for chips SR16 did not serialize separately.

    The previous global-stub experiment proved that unrelated optional chunks
    can make snes9x load the snapshot and then crash on the first emulated
    frame. Keep standalone output conservative: emit a missing-chip stub only
    when a structural source such as the neighboring ROM header identifies it.
    """
    return [
        (name, b"\x00" * size)
        for name, size in chip_stubs_for_source(sr16.source_name)
    ]


def _optional_chip_chunks_from_sr16(sr16: SR16Save) -> list[tuple[str, bytes]]:
    """Return snes9x optional chip chunks carried by SR16 tail sections."""
    chunks: list[tuple[str, bytes]] = []

    # Star Fox/SuperFX uses SR16's compact old SuperFX payload.
    sax = sr16.by_code("SAX")
    if sax is not None:
        sfx = _build_sfx_chunk_from_sax(sax.data)
        if sfx is not None:
            chunks.append(("SFX", sfx))

    chunks.extend(_build_sa1_chunks_from_sr16(sr16))

    # SR16 stores DSP-family state as a generic PSD payload. Write exactly one
    # snes9x DSP chunk: extra optional chunks are not harmless in snes9x 1.63.
    psd = sr16.by_code("PSD")
    if psd is not None and len(psd.data) == SR16_PSD_SIZE:
        name = _dsp_chunk_name_for_sr16_psd(sr16)
        chunks.append((name, _dsp_payload_from_sr16_psd_for_state(
            name, psd.data, sr16
        )))

    # Mega Man X2/X3 use Capcom's Cx4 chip. SR16 names the raw 8KB RAM chunk
    # "4XC"; snes9x expects the same bytes as "CX4".
    c4 = sr16.by_code("4XC")
    if c4 is not None and len(c4.data) == SR16_4XC_SIZE:
        chunks.append(("CX4", c4.data))

    present = {name for name, _data in chunks}
    for name, data in _compatibility_stub_chip_chunks(sr16):
        if name not in present:
            chunks.append((name, data))
            present.add(name)

    return chunks
