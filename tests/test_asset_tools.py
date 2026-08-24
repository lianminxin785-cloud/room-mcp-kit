from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

from tools.process_character_assets import required_frames


ROOT = Path(__file__).resolve().parents[1]


def transparent_subject(path: Path, size: tuple[int, int] = (120, 240)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 10, 90, 230), fill=(180, 110, 90, 255))
    image.save(path)


class AssetToolTests(unittest.TestCase):
    def test_character_cli_validates_and_writes_complete_outfit(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            input_root = base / "input"
            web_root = base / "web"
            output_root = web_root / "room" / "assets" / "character-packs"
            pack_path = base / "character-pack.json"
            pack_path.write_text(json.dumps({
                "schemaVersion": "room-character-pack-v1",
                "roles": {},
            }), encoding="utf-8")
            for source_name, *_rest in required_frames():
                transparent_subject(input_root / source_name)

            subprocess.run([
                sys.executable,
                str(ROOT / "tools" / "process_character_assets.py"),
                "--input", str(input_root),
                "--role", "owner",
                "--outfit", "default",
                "--display-name", "You",
                "--output-root", str(output_root),
                "--pack", str(pack_path),
                "--web-root", str(web_root),
            ], check=True, capture_output=True, text=True)

            outputs = list((output_root / "owner" / "default").rglob("*.png"))
            self.assertEqual(18, len(outputs))
            for output in outputs:
                with Image.open(output) as image:
                    self.assertEqual("RGBA", image.mode)
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
            role = pack["roles"]["owner"]
            self.assertEqual("default", role["defaultOutfit"])
            self.assertIn("default", role["outfits"])
            self.assertIn("room/assets/character-packs/owner/default", json.dumps(role))

    def test_character_cli_stops_before_writing_when_a_frame_is_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            input_root = base / "input"
            for source_name, *_rest in required_frames()[:-1]:
                transparent_subject(input_root / source_name)
            output_root = base / "web" / "out"
            pack_path = base / "character-pack.json"
            pack_path.write_text('{"schemaVersion":"room-character-pack-v1","roles":{}}', encoding="utf-8")
            result = subprocess.run([
                sys.executable,
                str(ROOT / "tools" / "process_character_assets.py"),
                "--input", str(input_root),
                "--role", "owner",
                "--output-root", str(output_root),
                "--pack", str(pack_path),
                "--web-root", str(base / "web"),
            ], capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(output_root.exists())

    def test_furniture_cli_updates_one_texture_without_touching_source(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            web_root = base / "web"
            source = base / "source.png"
            output = web_root / "room" / "assets" / "chair.png"
            manifest_path = base / "furniture-manifest.json"
            transparent_subject(source, (300, 200))
            source_bytes = source.read_bytes()
            manifest_path.write_text(json.dumps({
                "schemaVersion": "room-furniture-v1",
                "textures": {"existing": "room/existing.png"},
            }), encoding="utf-8")

            subprocess.run([
                sys.executable,
                str(ROOT / "tools" / "process_furniture_asset.py"),
                "--input", str(source),
                "--output", str(output),
                "--canvas", "160x120",
                "--texture-key", "v2-chair-back",
                "--manifest", str(manifest_path),
                "--web-root", str(web_root),
            ], check=True, capture_output=True, text=True)

            self.assertEqual(source_bytes, source.read_bytes())
            with Image.open(output) as image:
                self.assertEqual((160, 120), image.size)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("room/assets/chair.png", manifest["textures"]["v2-chair-back"])
            self.assertIn("existing", manifest["textures"])

    def test_background_cli_resizes_without_overwriting_input(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "background.png"
            output = base / "room-square.png"
            Image.new("RGB", (80, 50), (200, 180, 160)).save(source)
            source_bytes = source.read_bytes()
            subprocess.run([
                sys.executable,
                str(ROOT / "tools" / "process_room_background.py"),
                "--input", str(source),
                "--output", str(output),
                "--size", "64x64",
                "--sampling", "nearest",
            ], check=True, capture_output=True, text=True)
            self.assertEqual(source_bytes, source.read_bytes())
            with Image.open(output) as image:
                self.assertEqual((64, 64), image.size)


if __name__ == "__main__":
    unittest.main()
