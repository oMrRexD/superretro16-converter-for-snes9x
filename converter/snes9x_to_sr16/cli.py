"""CLI for the snes9x -> SuperRetro16 reverse converter."""
from __future__ import annotations
import argparse
import sys

from .pipeline import snes9x_to_sr16


def main(argv=None, *, prog: str | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Convert snes9x v12 .000 save states to SuperRetro16 .s0X format.",
        prog=prog,
    )
    parser.add_argument("input", help="snes9x .000 save state (gzipped or raw)")
    parser.add_argument("output", help="output SR16 .s0X file path")
    parser.add_argument(
        "--rom", default=None,
        help="deprecated; screenshots are built from the save's SHO chunk",
    )
    parser.add_argument(
        "--no-ssz", action="store_true",
        help="skip SSZ (old SoundData) section synthesis",
    )
    parser.add_argument(
        "--no-png", action="store_true",
        help="skip PNG (screenshot) section synthesis",
    )
    parser.add_argument(
        "--dump", action="store_true",
        help="dump snes9x chunk info instead of converting",
    )

    args = parser.parse_args(argv)

    try:
        snes9x_to_sr16(
            args.input,
            args.output,
            rom_path=args.rom,
            include_ssz=not args.no_ssz,
            include_png=not args.no_png,
            dump=args.dump,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
