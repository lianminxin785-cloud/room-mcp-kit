from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class RoomSettings:
    token: str
    db_path: Path
    initial_state_path: Path
    map_path: Path

    @classmethod
    def from_env(cls) -> "RoomSettings":
        return cls(
            token=os.environ.get("ROOM_TOKEN", "").strip(),
            db_path=Path(os.environ.get("ROOM_DB", ROOT / "room_service" / "data" / "room.db")),
            initial_state_path=Path(
                os.environ.get("ROOM_INITIAL_STATE", ROOT / "web" / "room" / "data" / "initial-state.json")
            ),
            map_path=Path(
                os.environ.get("ROOM_MAP", ROOT / "web" / "room" / "data" / "room-map.json")
            ),
        ).validate()

    def validate(self) -> "RoomSettings":
        if len(self.token) < 16:
            raise RuntimeError("ROOM_TOKEN must contain at least 16 characters")
        if self.db_path.exists() and self.db_path.is_dir():
            raise RuntimeError("ROOM_DB must be a file path")
        if not self.initial_state_path.is_file():
            raise RuntimeError("ROOM_INITIAL_STATE must be an existing JSON file")
        if not self.map_path.is_file():
            raise RuntimeError("ROOM_MAP must be an existing JSON file")
        return self
