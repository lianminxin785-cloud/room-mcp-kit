"""Normalize one Room character outfit and register it in character-pack.json."""

from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import re

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
DEFAULT_OUTPUT_ROOT = WEB_ROOT / "room" / "assets" / "room-v2" / "game" / "character-packs"
DEFAULT_PACK = WEB_ROOT / "room" / "assets" / "room-v2" / "config" / "character-pack.json"
DIRECTIONS = ("down", "left", "up", "right")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def required_frames() -> list[tuple[str, str, tuple[int, int], tuple[int, int], str]]:
    frames: list[tuple[str, str, tuple[int, int], tuple[int, int], str]] = []
    for direction in DIRECTIONS:
        frames.append((f"idle/{direction}.png", f"idle/{direction}.png", (192, 304), (96, 296), "locomotion"))
        for index in (0, 1):
            frames.append((
                f"walk/{direction}-{index}.png",
                f"walk/{direction}-{index}.png",
                (192, 304),
                (96, 296),
                "locomotion",
            ))
    for pose in ("sit", "read"):
        frames.append((f"actions/{pose}.png", f"actions/{pose}.png", (192, 280), (96, 152), "seated"))
    for index in (0, 1):
        frames.append((f"actions/work-{index}.png", f"actions/work-{index}.png", (192, 280), (96, 152), "seated"))
    for pose in ("sleep", "rest"):
        frames.append((f"actions/{pose}.png", f"actions/{pose}.png", (224, 336), (112, 62), "lying"))
    return frames


def clean_alpha(source: Image.Image, threshold: int) -> Image.Image:
    if "A" not in source.getbands():
        raise ValueError("character source must contain an alpha channel")
    rgba = source.convert("RGBA")
    alpha = rgba.getchannel("A").point(lambda value: 255 if value >= threshold else 0)
    rgba.putalpha(alpha)
    if alpha.getbbox() is None:
        raise ValueError("character source has no visible pixels")
    return rgba


def normalize_frame(
    source: Image.Image,
    *,
    canvas_size: tuple[int, int],
    anchor: tuple[int, int],
    target_height: int,
    source_anchor_ratio: float,
    threshold: int,
) -> Image.Image:
    cleaned = clean_alpha(source, threshold)
    bounds = cleaned.getchannel("A").getbbox()
    assert bounds is not None
    subject = cleaned.crop(bounds)
    scale = min(target_height / subject.height, (canvas_size[0] - 4) / subject.width)
    size = (max(1, round(subject.width * scale)), max(1, round(subject.height * scale)))
    subject = subject.resize(size, Image.Resampling.NEAREST)
    left = round(anchor[0] - subject.width / 2)
    top = round(anchor[1] - subject.height * source_anchor_ratio)
    if left < 0 or top < 0 or left + subject.width > canvas_size[0] or top + subject.height > canvas_size[1]:
        raise ValueError("normalized character does not fit the target canvas; adjust the source crop or target height")
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    canvas.alpha_composite(subject, (left, top))
    return canvas


def web_path(path: Path, web_root: Path = WEB_ROOT) -> str:
    try:
        return path.resolve().relative_to(web_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("character output must stay inside the repository web directory") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize a complete Room character outfit with NEAREST sampling.")
    parser.add_argument("--input", type=Path, required=True, help="Directory containing idle/, walk/ and actions/.")
    parser.add_argument("--role", required=True, help="Public role or custom character id, for example owner.")
    parser.add_argument("--outfit", default="default", help="Outfit id, for example default or sleepwear.")
    parser.add_argument("--display-name", default="", help="Display name used when creating or updating the role.")
    parser.add_argument("--label-background", default="#765f59")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--web-root", type=Path, default=WEB_ROOT)
    parser.add_argument("--locomotion-height", type=int, default=248)
    parser.add_argument("--seated-height", type=int, default=224)
    parser.add_argument("--lying-height", type=int, default=264)
    parser.add_argument("--hip-ratio", type=float, default=0.56)
    parser.add_argument("--pillow-ratio", type=float, default=0.16)
    parser.add_argument("--alpha-threshold", type=int, default=48)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not SLUG.fullmatch(args.role) or not SLUG.fullmatch(args.outfit):
        raise SystemExit("--role and --outfit must use lowercase letters, numbers and hyphens")
    if not 1 <= args.alpha_threshold <= 254:
        raise SystemExit("--alpha-threshold must be between 1 and 254")
    if not 0 < args.hip_ratio < 1 or not 0 < args.pillow_ratio < 1:
        raise SystemExit("anchor ratios must be between 0 and 1")

    height_by_family = {
        "locomotion": args.locomotion_height,
        "seated": args.seated_height,
        "lying": args.lying_height,
    }
    ratio_by_family = {"locomotion": 1.0, "seated": args.hip_ratio, "lying": args.pillow_ratio}
    contracts = required_frames()
    missing = [str(args.input / source) for source, *_rest in contracts if not (args.input / source).is_file()]
    if missing:
        raise SystemExit("Missing required character frames:\n" + "\n".join(missing))

    rendered: dict[Path, bytes] = {}
    output_dir = args.output_root / args.role / args.outfit
    for source_name, output_name, canvas, anchor, family in contracts:
        with Image.open(args.input / source_name) as source:
            normalized = normalize_frame(
                source,
                canvas_size=canvas,
                anchor=anchor,
                target_height=height_by_family[family],
                source_anchor_ratio=ratio_by_family[family],
                threshold=args.alpha_threshold,
            )
        buffer = BytesIO()
        normalized.save(buffer, format="PNG", optimize=True)
        rendered[output_dir / output_name] = buffer.getvalue()

    pack = json.loads(args.pack.read_text(encoding="utf-8"))
    if pack.get("schemaVersion") != "room-character-pack-v1":
        raise SystemExit("Unsupported character pack schema")
    role = pack["roles"].get(args.role, {})
    display_name = args.display_name or role.get("displayName") or args.role.replace("-", " ").title()
    prefix = web_path(output_dir, args.web_root)
    idle = {direction: f"{prefix}/idle/{direction}.png" for direction in DIRECTIONS}
    walk = {
        direction: {str(index): f"{prefix}/walk/{direction}-{index}.png" for index in (0, 1)}
        for direction in DIRECTIONS
    }
    actions = {
        "sit": f"{prefix}/actions/sit.png",
        "read": f"{prefix}/actions/read.png",
        "work": {str(index): f"{prefix}/actions/work-{index}.png" for index in (0, 1)},
        "sleep": f"{prefix}/actions/sleep.png",
        "rest": f"{prefix}/actions/rest.png",
    }
    outfits = dict(role.get("outfits") or {})
    outfits[args.outfit] = {"frames": {"idle": idle, "walk": walk, "actions": actions}}
    pack["roles"][args.role] = {
        "displayName": display_name,
        "labelBackground": args.label_background or role.get("labelBackground") or "#765f59",
        "displaySize": role.get("displaySize") or [192, 304],
        "defaultOutfit": role.get("defaultOutfit") or args.outfit,
        "outfits": outfits,
    }

    for path, content in rendered.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    args.pack.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Processed {len(rendered)} frames for {args.role}/{args.outfit}")
    print(f"Updated {args.pack}")


if __name__ == "__main__":
    main()
