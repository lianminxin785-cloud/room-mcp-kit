from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
ROOM = WEB / "room"
CONFIG = ROOM / "assets" / "room-v2" / "config"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class RoomFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial = load_json(ROOM / "data" / "initial-state.json")
        cls.furniture = load_json(CONFIG / "furniture-manifest.json")
        cls.characters = load_json(CONFIG / "character-pack.json")
        cls.actions = load_json(CONFIG / "action-pack.json")
        cls.html = (WEB / "index.html").read_text(encoding="utf-8")
        cls.scene = (ROOM / "scenes" / "RoomScene.js").read_text(encoding="utf-8")
        cls.main = (ROOM / "main.js").read_text(encoding="utf-8")
        cls.client = (ROOM / "RoomServiceClient.js").read_text(encoding="utf-8")

    def test_manifests_are_split_and_use_public_roles(self):
        self.assertEqual("room-furniture-v1", self.furniture["schemaVersion"])
        self.assertEqual("room-character-pack-v1", self.characters["schemaVersion"])
        self.assertEqual("room-action-pack-v1", self.actions["schemaVersion"])
        self.assertEqual({"owner", "companion"}, set(self.characters["roles"]))
        self.assertEqual({"owner", "companion"}, {item["id"] for item in self.initial["characters"]})
        self.assertFalse((CONFIG / "manifest.json").exists())

    def test_public_character_pack_uses_only_neutral_example_assets(self):
        for role in self.characters["roles"].values():
            self.assertIn(role["defaultOutfit"], role["outfits"])
            paths = set(role["outfits"][role["defaultOutfit"]]["frames"].values())
            self.assertEqual(1, len(paths))
            for relative in paths:
                self.assertIn("game/example-characters/", relative)
                self.assertTrue((WEB / relative).is_file(), relative)

    def test_furniture_manifest_paths_and_initial_texture_keys_exist(self):
        textures = self.furniture["textures"]
        for relative in [self.furniture["background"]["path"], *textures.values()]:
            self.assertTrue((WEB / relative).is_file(), relative)

        used = set()
        for furniture in self.initial["furniture"]:
            for layer in furniture["layers"]:
                if "texture" in layer:
                    used.add(layer["texture"])
                used.update((layer.get("textures") or {}).values())
        self.assertEqual(set(), used - set(textures))

    def test_optional_duo_pack_defaults_to_individual_actor_fallback(self):
        self.assertEqual([], self.actions["duoActions"])
        self.assertIn("this.actionPack.duoActions ?? []", self.scene)
        self.assertIn("this.placeActorAtFurnitureAction(actor, entry)", self.scene)
        self.assertNotIn("duo-calibration", self.scene)
        self.assertNotIn("book-calibration", self.scene)

    def test_standalone_page_has_no_chat_or_private_config_dependency(self):
        self.assertIn('data-character-card="owner"', self.html)
        self.assertIn('data-character-card="companion"', self.html)
        self.assertNotIn("room/chat.js", self.html)
        self.assertNotIn("config.js", self.html)
        self.assertNotIn("room-chat-panel", self.html)
        self.assertIn("furniture-manifest.json", self.main)
        self.assertIn("character-pack.json", self.main)
        self.assertIn("action-pack.json", self.main)
        self.assertIn('sceneId: "home"', self.scene)

    def test_browser_api_controls_owner_only(self):
        self.assertIn('characters/owner/move', self.client)
        self.assertIn('characters/owner/use', self.client)
        self.assertIn('characters/owner/stop', self.client)
        self.assertNotIn('characters/companion/move', self.client)


if __name__ == "__main__":
    unittest.main()
