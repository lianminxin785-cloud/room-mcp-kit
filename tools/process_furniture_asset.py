"""Normalize one transparent furniture layer and register its runtime texture."""

from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
DEFAULT_MANIFEST = WEB_ROOT / "room" / "assets" / "room-v2" / "config" / "furniture-manifest.json"


def parse_size(value: str) -> tuple[int, int]:
    try:
        width, height = (int(part) for part in value.lower().split("x", 1))
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("size must look like WIDTHxHEIGHT") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("size values must be positive")
    return width, height


def normalize(source: Image.Image, canvas_size: tuple[int, int], threshold: int) -> Image.Image:
    if "A" not in source.getbands():
        raise ValueError("furniture source must contain an alpha channel")
    rgba = source.convert("RGBA")
    alpha = rgba.getchannel("A").point(lambda value: 255 if value >= threshold else 0)
    rgba.putalpha(alpha)
    bounds = alpha.getbbox()
    if bounds is None:
        raise ValueError("furniture source has no visible pixels")
    subject = rgba.crop(bounds)
    scale = min(canvas_size[0] / subject.width, canvas_size[1] / subject.height)
    size = (max(1, round(subject.width * scale)), max(1, round(subject.height * scale)))
    subject = subject.resize(size, Image.Resampling.NEAREST)
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    canvas.alpha_composite(subject, ((canvas_size[0] - subject.width) // 2, canvas_size[1] - subject.height))
    return canvas


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize one manually cropped Room furniture layer.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--canvas", type=parse_size, required=True, help="Runtime canvas, for example 440x440.")
    parser.add_argument("--texture-key", required=True, help="Texture key referenced by initial-state.json.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--web-root", type=Path, default=WEB_ROOT)
    parser.add_argument("--alpha-threshold", type=int, default=48)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.input.is_file():
        raise SystemExit(f"Input does not exist: {args.input}")
    if not 1 <= args.alpha_threshold <= 254:
        raise SystemExit("--alpha-threshold must be between 1 and 254")
    try:
        runtime_path = args.output.resolve().relative_to(args.web_root.resolve()).as_posix()
    except ValueError as exc:
        raise SystemExit("--output must stay inside the repository web directory") from exc

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != "room-furniture-v1":
        raise SystemExit("Unsupported furniture manifest schema")
    with Image.open(args.input) as source:
        result = normalize(source, args.canvas, args.alpha_threshold)
    buffer = BytesIO()
    result.save(buffer, format="PNG", optimize=True)

    manifest["textures"][args.texture_key] = runtime_path
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(buffer.getvalue())
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Built furniture layer: {runtime_path}")
    print(f"Updated texture key: {args.texture_key}")


if __name__ == "__main__":
    main()
