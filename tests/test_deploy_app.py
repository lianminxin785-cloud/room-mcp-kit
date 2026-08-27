from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from room_service.config import ROOT, RoomSettings
from room_service.deploy_app import create_deploy_app


class DeployAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.token = "test-room-token-123456"
        settings = RoomSettings(
            token=self.token,
            db_path=Path(self.temp.name) / "room.db",
            initial_state_path=ROOT / "web" / "room" / "data" / "initial-state.json",
            map_path=ROOT / "web" / "room" / "data" / "room-map.json",
        )
        self.client_context = TestClient(create_deploy_app(settings))
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.temp.cleanup()

    def test_health_is_public_and_room_is_private(self):
        self.assertEqual(200, self.client.get("/healthz").status_code)
        self.assertEqual(401, self.client.get("/").status_code)
        self.assertEqual(401, self.client.get("/api/v1/room/state").status_code)

    def test_browser_token_becomes_secure_cookie(self):
        response = self.client.get(f"/?token={self.token}", follow_redirects=False)
        self.assertEqual(303, response.status_code)
        self.assertEqual("/", response.headers["location"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("Secure", response.headers["set-cookie"])

    def test_authorized_room_api_uses_shared_store(self):
        headers = {"Authorization": f"Bearer {self.token}"}
        state = self.client.get("/api/v1/room/state", headers=headers)
        self.assertEqual(200, state.status_code)
        self.assertEqual({"owner", "companion"}, {c["id"] for c in state.json()["characters"]})

    def test_mcp_requires_token(self):
        self.assertEqual(401, self.client.post("/mcp").status_code)

    def test_mcp_initializes_with_query_token(self):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        }
        response = self.client.post(
            f"/mcp/?token={self.token}",
            json=payload,
            headers={"Accept": "application/json, text/event-stream"},
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual("room-mcp-kit", response.json()["result"]["serverInfo"]["name"])


if __name__ == "__main__":
    unittest.main()
