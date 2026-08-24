from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from room_service.app import create_app
from room_service.config import RoomSettings
from room_service.core import RoomStore, utc_now
from room_service.mcp_server import execute_tool, tool_models


ROOT = Path(__file__).resolve().parents[1]
INITIAL = ROOT / "web" / "room" / "data" / "initial-state.json"
MAP = ROOT / "web" / "room" / "data" / "room-map.json"


class RoomStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RoomStore(
            Path(self.temp.name) / "room.db",
            initial_state_path=INITIAL,
            map_path=MAP,
        )
        self.store.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def test_snapshot_uses_public_scene_and_configured_character_names(self):
        state = self.store.snapshot(detail="full")
        self.assertEqual("home", state["scene"]["id"])
        characters = {item["id"]: item for item in state["characters"]}
        self.assertEqual({"owner", "companion"}, set(characters))
        self.assertEqual("You", characters["owner"]["display_name"])
        self.assertEqual("Companion", characters["companion"]["display_name"])

        regions = {item["id"]: item for item in state["semantic_map"]["regions"]}
        overlap = 75 * 100 + 34
        self.assertIn(overlap, regions["rug"]["tiles"])
        self.assertIn(overlap, regions["coffee-table"]["tiles"])
        self.assertFalse(regions["rug"]["blocking"])

    def test_fixed_sofa_slots_become_together_state(self):
        now = utc_now()
        self.store.use_furniture("owner", "sofa", "sit", now=now)
        moving = self.store.use_furniture("companion", "sofa", "sit", now=now)
        sofa = next(item for item in moving["furniture"] if item["id"] == "sofa")
        self.assertEqual(
            {("owner", "sit", "seatLeft"), ("companion", "sit", "seatRight")},
            {
                (item["character_id"], item["interaction"], item["slot_id"])
                for item in sofa["occupants"]
            },
        )

        characters = {
            item["id"]: item
            for item in self.store.snapshot(now=now + timedelta(minutes=2))["characters"]
        }
        self.assertEqual("sit_together", characters["owner"]["activity"])
        self.assertEqual("sit_together", characters["companion"]["activity"])
        self.assertEqual("companion", characters["owner"]["together_with"])
        self.assertEqual("owner", characters["companion"]["together_with"])

        self.store.stop("companion", now=now + timedelta(minutes=3))
        characters = {item["id"]: item for item in self.store.snapshot()["characters"]}
        self.assertEqual("sit", characters["owner"]["activity"])
        self.assertEqual("idle", characters["companion"]["activity"])

    def test_bookcase_keeps_owner_and_companion_in_fixed_slots(self):
        now = utc_now()
        self.store.use_furniture("owner", "bookcase", "read", now=now)
        moving = self.store.use_furniture("companion", "bookcase", "read", now=now)
        bookcase = next(item for item in moving["furniture"] if item["id"] == "bookcase")
        self.assertEqual(
            {("owner", "readOwner"), ("companion", "readCompanion")},
            {(item["character_id"], item["slot_id"]) for item in bookcase["occupants"]},
        )

        characters = {
            item["id"]: item
            for item in self.store.snapshot(now=now + timedelta(minutes=2))["characters"]
        }
        self.assertEqual("read_together", characters["owner"]["activity"])
        self.assertEqual("read_together", characters["companion"]["activity"])

    def test_mcp_exposes_four_tools_and_only_moves_companion(self):
        self.assertEqual(
            ["room_get_state", "room_move", "room_use_furniture", "room_stop"],
            [tool.name for tool in tool_models()],
        )
        move_schema = next(tool for tool in tool_models() if tool.name == "room_move").input_schema
        self.assertEqual(
            ["owner"],
            move_schema["properties"]["target"]["properties"]["character_id"]["enum"],
        )

        before = {item["id"]: item for item in self.store.snapshot()["characters"]}
        result, error = execute_tool(
            self.store,
            "room_move",
            {"target": {"kind": "tile", "x": 48, "y": 72}},
        )
        self.assertFalse(error)
        after = {item["id"]: item for item in result["characters"]}
        self.assertEqual(before["owner"]["position"], after["owner"]["position"])
        self.assertEqual("moving", after["companion"]["activity"])

    def test_layout_changes_are_owned_by_owner(self):
        with self.assertRaisesRegex(ValueError, "layout_owner_must_be_owner"):
            self.store.update_layout(
                {"sofa": {"x": 272, "y": 1280}},
                actor_id="companion",
            )

    def test_mood_field_accepts_generic_external_updates(self):
        changed = self.store.apply_moods(
            {
                "owner": {
                    "code": "happy",
                    "label": "Happy",
                    "revision": 1,
                    "updated_at": "now",
                    "source": "external",
                }
            }
        )
        self.assertTrue(changed)
        owner = next(item for item in self.store.snapshot()["characters"] if item["id"] == "owner")
        self.assertEqual("external", owner["mood"]["source"])
        self.assertEqual("character_moods_updated", self.store.events_after(0)[-1]["type"])


class RoomAppTests(unittest.TestCase):
    def test_rest_requires_token_and_only_controls_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = RoomSettings(
                token="room-test-secret-value",
                db_path=Path(temp) / "room.db",
                initial_state_path=INITIAL,
                map_path=MAP,
            ).validate()
            app = create_app(settings)
            with TestClient(app) as client:
                self.assertEqual(401, client.get("/api/v1/room/state").status_code)
                headers = {"X-Room-Token": settings.token}

                health = client.get("/api/v1/room/health", headers=headers)
                self.assertEqual(200, health.status_code)
                self.assertEqual("home", health.json()["scene_id"])
                self.assertEqual(
                    {"ok", "scene_id", "revision", "event_cursor"},
                    set(health.json()),
                )

                moved = client.post(
                    "/api/v1/room/characters/owner/move",
                    headers=headers,
                    json={"target": {"kind": "tile", "x": 31, "y": 70}},
                )
                self.assertEqual(200, moved.status_code)
                self.assertEqual(
                    404,
                    client.post(
                        "/api/v1/room/characters/companion/move",
                        headers=headers,
                        json={"target": {"kind": "tile", "x": 48, "y": 72}},
                    ).status_code,
                )


if __name__ == "__main__":
    unittest.main()
