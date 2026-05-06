"""Command-line interface for SaveShift conversions.

Preferred commands:
    py -m converter sr16-to-snes9x <input.s0X> <output.000>
    py -m converter snes9x-to-sr16 <input.000> <output.s0X>
    py -m converter extract-sram <input.s0X|input.000> <output.srm>
    py -m converter dump <input.s0X|input.000>

Simple auto-detect invocations are also accepted:
    py -m converter <input.s0X> <output.000> [--template <ref.000>]
    py -m converter <input.000> <output.s0X>
    py -m converter <input.s0X> <output.srm> --srm
    py -m converter <input.s0X> --dump
"""
from __future__ import annotations

import argparse
import gzip
import sys
from pathlib import Path

from .common.format.snes9x import parse_snes9x
from .common.format.sr16 import SR16_MAGIC_PREFIX, parse_sr16
from .sr16_to_snes9x.pipeline import build_snes9x, extract_chunks_from_sr16


_COMMANDS = {"sr16-to-snes9x", "snes9x-to-sr16", "extract-sram", "dump"}


def _read(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _write(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def _write_snes9x(path: str, plain: bytes) -> None:
    with open(path, "wb") as raw, \
         gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=6, mtime=0) as f:
        f.write(plain)


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


def _extract_sram(data: bytes, filename: str) -> bytes:
    if data.startswith(SR16_MAGIC_PREFIX):
        sr16 = parse_sr16(data, filename, lenient=False)
        section = sr16.by_code("S01")
        if section is None:
            raise ValueError("SR16 save has no S01/SRAM section")
        return _trim_sram(section.data)

    chunks = parse_snes9x(data)
    sra = chunks.get("SRA")
    if sra is None:
        raise ValueError("snes9x save has no SRA/SRAM chunk")
    return _trim_sram(sra)


def _convert_sr16_to_snes9x(args) -> None:
    sr16_blob = _read(args.input)
    sr16 = parse_sr16(
        sr16_blob,
        str(Path(args.input)),
        lenient=getattr(args, "lenient", False),
    )

    if args.template:
        template = parse_snes9x(_read(args.template))
        flags = []
        if args.template_reg:
            flags.append("REG")
        if args.template_ram:
            flags.append("RAM")
        mode = "template" + ("+" + "+".join(flags) if flags else "")
        print(f"using {mode}: {args.template}")
    else:
        if args.template_reg or args.template_ram:
            raise ValueError("--template-reg/--template-ram require --template")
        template = extract_chunks_from_sr16(
            sr16,
            vram_dma_mode=getattr(args, "vram_dma", "off"),
        )
        print("standalone mode (all regions from SR16)")

    plain = build_snes9x(
        sr16,
        template,
        use_template_reg=args.template_reg,
        use_template_ram=args.template_ram,
    )
    _write_snes9x(args.output, plain)
    print(f"wrote {args.output}  (uncompressed {len(plain)} bytes)")


def _cmd_extract_sram(args) -> None:
    data = _read(args.input)
    sram = _extract_sram(data, args.input)
    _write(args.output, sram)
    print(f"wrote {args.output}  ({len(sram)} bytes, SRAM battery save)")


def _cmd_snes9x_to_sr16(args) -> None:
    from .snes9x_to_sr16.pipeline import snes9x_to_sr16

    if not args.output and not args.dump:
        raise ValueError("output is required unless --dump is used")
    snes9x_to_sr16(
        args.input,
        args.output or "",
        rom_path=args.rom,
        include_ssz=not args.no_ssz,
        include_png=not args.no_png,
        dump=args.dump,
    )


def _dump_sr16(data: bytes, filename: str, *, lenient: bool) -> None:
    sr16 = parse_sr16(data, filename, lenient=lenient)
    for s in sr16.sections:
        print(f"  {s.code}  size={s.size:7d}  off=0x{s.offset:06x}")
    print(f"  trailer: {len(sr16.trailer)} bytes")
    present = {s.code for s in sr16.sections}
    required = ("C01", "P01", "D01", "VR1", "RM1", "S01", "F01")
    missing = [code for code in required if code not in present]
    if missing:
        print(
            f"  WARNING: missing required section(s): {', '.join(missing)}"
            " — conversion will fail.",
            file=sys.stderr,
        )


def _dump_snes9x(data: bytes, filename: str) -> None:
    chunks = parse_snes9x(data)
    print(f"snes9x save: {filename}")
    print(f"  chunks: {len(chunks)}")
    for code, payload in chunks.items():
        print(f"  {code}  size={len(payload):7d}")


def _cmd_dump(args) -> None:
    data = _read(args.input)
    if data.startswith(SR16_MAGIC_PREFIX):
        _dump_sr16(data, args.input, lenient=args.lenient)
    else:
        _dump_snes9x(data, args.input)


def _is_sr16_slot_path(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return (
        len(suffix) >= 3
        and suffix.startswith(".s")
        and suffix[2:].isdigit()
        and 0 <= int(suffix[2:]) <= 999
    )


def _looks_like_snes9x_state(data: bytes) -> bool:
    try:
        parse_snes9x(data)
    except ValueError:
        return False
    return True


def _add_forward_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--template",
                        help="reference snes9x slot state to source struct + chip chunks from")
    parser.add_argument("--template-reg", action="store_true",
                        help="also source REG (CPU PC/SP) from template")
    parser.add_argument("--template-ram", action="store_true",
                        help="also source WRAM from template")
    parser.add_argument("--lenient", action="store_true",
                        help="accept SR16 saves where the trailing section is truncated")
    parser.add_argument("--vram-dma", choices=["off", "safe", "all"], default="off",
                        help="experimental armed VRAM DMA pre-exec mode")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="converter",
        description="Convert save states between SuperRetro16 and snes9x.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    forward = sub.add_parser(
        "sr16-to-snes9x",
        help="convert a SuperRetro16 save state to a snes9x slot state",
    )
    forward.add_argument("input")
    forward.add_argument("output")
    _add_forward_options(forward)
    forward.set_defaults(func=_convert_sr16_to_snes9x)

    reverse = sub.add_parser(
        "snes9x-to-sr16",
        help="convert a snes9x slot state to a SuperRetro16 save state",
    )
    reverse.add_argument("input")
    reverse.add_argument("output", nargs="?")
    reverse.add_argument("--rom", default=None,
                         help="deprecated; screenshots are built from the save's SHO chunk")
    reverse.add_argument("--no-ssz", action="store_true",
                         help="skip SSZ (old SoundData) section synthesis")
    reverse.add_argument("--no-png", action="store_true",
                         help="skip PNG (screenshot) section synthesis")
    reverse.add_argument("--dump", action="store_true",
                         help="dump snes9x chunk info instead of converting")
    reverse.set_defaults(func=_cmd_snes9x_to_sr16)

    sram = sub.add_parser(
        "extract-sram",
        help="extract raw SRAM from an SR16 or snes9x save state",
    )
    sram.add_argument("input")
    sram.add_argument("output")
    sram.set_defaults(func=_cmd_extract_sram)

    dump = sub.add_parser("dump", help="print SR16 sections or snes9x chunks")
    dump.add_argument("input")
    dump.add_argument("--lenient", action="store_true",
                      help="accept SR16 saves where the trailing section is truncated")
    dump.set_defaults(func=_cmd_dump)

    return parser


def _auto_main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        description="Auto-detect and convert SR16/snes9x save states.",
    )
    parser.add_argument("input")
    parser.add_argument("output", nargs="?")
    _add_forward_options(parser)
    parser.add_argument("--srm", action="store_true",
                        help="extract SRAM as .srm battery save")
    parser.add_argument("--dump", action="store_true",
                        help="print parsed SR16 sections and exit")
    args = parser.parse_args(argv)

    if args.dump:
        data = _read(args.input)
        if data.startswith(SR16_MAGIC_PREFIX):
            _dump_sr16(data, args.input, lenient=True)
        else:
            _dump_snes9x(data, args.input)
        return

    if not args.output:
        raise ValueError("output is required when not --dump")

    if args.srm:
        _cmd_extract_sram(args)
        print("Place this .srm next to your ROM file, then load the ROM")
        print("in snes9x and use the in-game load screen.")
        return

    data = _read(args.input)
    if data.startswith(SR16_MAGIC_PREFIX):
        _convert_sr16_to_snes9x(args)
        return

    if _looks_like_snes9x_state(data):
        if not _is_sr16_slot_path(args.output):
            raise ValueError(
                "snes9x input detected; use an SR16 output name such as "
                "output.s01, or use the explicit snes9x-to-sr16 subcommand"
            )
        args.rom = None
        args.no_ssz = False
        args.no_png = False
        _cmd_snes9x_to_sr16(args)
        return

    raise ValueError(
        "could not auto-detect input format as SuperRetro16 or snes9x save state"
    )


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv is None and Path(sys.argv[0]).stem.lower() == "sr16-to-snes9x":
            _auto_main(args)
            return
        if args and args[0] not in _COMMANDS and args[0] not in ("-h", "--help"):
            _auto_main(args)
            return
        parser = _build_parser()
        parsed = parser.parse_args(args)
        parsed.func(parsed)
    except Exception as exc:
        raise SystemExit(f"error: {exc}") from exc


if __name__ == "__main__":
    main()
