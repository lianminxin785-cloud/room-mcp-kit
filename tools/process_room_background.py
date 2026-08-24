"""Resize one Room background into the configured square world canvas."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "web" / "room" / "assets" / "room-v2" / "source" / "manual" / "background" / "background.png"
DEFAULT_OUTPUT = ROOT / "web" / "room" / "assets" / "room-v2" / "game" / "background" / "room-square.png"


def parse_size(value: str) -> tuple[int, int]:
    try:
        width, height = (int(part) for part in value.lower().split("x", 1))
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("size must look like WIDTHxHEIGHT") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("size values must be positive")
    return width, height


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resize a Room background without changing the source file.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--size", type=parse_size, default=(1600, 1600))
    parser.add_argument("--sampling", choices=("nearest", "lanczos"), default="lanczos")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.input.is_file():
        raise SystemExit(f"Input does not exist: {args.input}")
    sampling = Image.Resampling.NEAREST if args.sampling == "nearest" else Image.Resampling.LANCZOS
    with Image.open(args.input) as source:
        output = source.convert("RGB").resize(args.size, sampling)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.save(args.output, optimize=True)
    print(f"Built background: {args.output}")


if __name__ == "__main__":
    main()
