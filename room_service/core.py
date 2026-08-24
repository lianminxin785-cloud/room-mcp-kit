from __future__ import annotations

from collections import deque
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any


UTC = timezone.utc
CHARACTER_IDS = frozenset({"owner", "companion"})
DEFAULT_DISPLAY_NAMES = {"owner": "You", "companion": "Companion"}
FURNITURE_ID_ALIASES = {"computer": "workstation", "workstation": "workstation"}
RUNTIME_FURNITURE_IDS = {"workstation": "computer"}
INTERACTION_ACTIVITIES = {
    "sleep": "sleep",
    "rest": "rest",
    "sit": "sit",
    "work": "work",
    "read": "read",
    "toggle_tv": "watch_tv",
}
TOGETHER_INTERACTIONS = frozenset({"sleep", "rest", "sit", "work", "read"})


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat(timespec="milliseconds")


def canonical_furniture_id(value: str) -> str:
    clean = str(value or "").strip()
    return FURNITURE_ID_ALIASES.get(clean, clean)


class RoomStore:
    """SQLite-backed authority for one shared Room scene.

    The database stores one compact JSON state plus append-only lightweight
    events. Map geometry and furniture definitions remain source controlled.
    """

    def __init__(
        self,
        path: Path,
        *,
        initial_state_path: Path,
        map_path: Path,
        step_seconds: float = 16 / 192,
    ):
        self.path = Path(path)
        self.initial_state_path = Path(initial_state_path)
        self.map_path = Path(map_path)
        self.step_seconds = max(0.001, float(step_seconds))
        self._lock = threading.RLock()
        self._initial = json.loads(self.initial_state_path.read_text(encoding="utf-8"))
        self._map = json.loads(self.map_path.read_text(encoding="utf-8"))
        self.scene_id = str(self._initial.get("scene", {}).get("id") or "home")
        self.scene_revision = int(self._initial.get("scene", {}).get("revision") or 1)
        self.map_width = int(self._map["width"])
        self.map_height = int(self._map["height"])
        self.tile_size = int(self._map["tilewidth"])
        wall_layer = next(layer for layer in self._map["layers"] if layer["name"] == "walls")
        self.wall_tiles = {
            index
            for index, value in enumerate(wall_layer["data"])
            if int(value) > 0
        }
        self._default_furniture = self._normalise_furniture(self._initial["furniture"])

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS room_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    revision INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS room_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    revision INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            if conn.execute("SELECT 1 FROM room_state WHERE id=1").fetchone() is None:
                state = self._seed_state()
                conn.execute(
                    "INSERT INTO room_state(id,revision,state_json,updated_at) VALUES(1,?,?,?)",
                    (0, self._dump(state), iso()),
                )
                self._event(conn, 0, "room_initialized", {"scene_id": self.scene_id})
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _dump(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _seed_state(self) -> dict[str, Any]:
        characters: dict[str, dict[str, Any]] = {}
        stamp = iso()
        for source in self._initial["characters"]:
            character_id = str(source["id"])
            if character_id not in CHARACTER_IDS:
                raise ValueError("initial_state_character_must_be_owner_or_companion")
            characters[character_id] = {
                "id": character_id,
                "display_name": str(
                    source.get("displayName")
                    or source.get("display_name")
                    or DEFAULT_DISPLAY_NAMES[character_id]
                ),
                "position": deepcopy(source["position"]),
                "direction": source.get("direction", "down"),
                "clothes": source.get("clothes", "default"),
                "mood": {
                    "code": str(source.get("emotion") or ""),
                    "label": "",
                    "revision": 0,
                    "updated_at": None,
                    "source": "initial",
                },
                "activity": "idle",
                "base_activity": "idle",
                "active_furniture_id": None,
                "interaction": None,
                "slot_id": None,
                "together_with": None,
                "movement": None,
                "updated_at": stamp,
            }
        if set(characters) != CHARACTER_IDS:
            raise ValueError("initial_state_requires_owner_and_companion")
        return {
            "contract_version": "room-state-v1",
            "scene": {
                "id": self.scene_id,
                "revision": self.scene_revision,
                "name": str(self._initial.get("scene", {}).get("name") or "My Room"),
                "world": {"width": 1600, "height": 1600},
                "grid": {
                    "width": self.map_width,
                    "height": self.map_height,
                    "tile_size": self.tile_size,
                },
            },
            "characters": characters,
            "furniture": deepcopy(self._default_furniture),
        }

    def _normalise_furniture(self, items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for source in items:
            runtime_id = str(source["id"])
            furniture_id = canonical_furniture_id(runtime_id)
            item = deepcopy(source)
            item["id"] = furniture_id
            item["runtime_id"] = runtime_id
            item["semantic_role"] = str(item.get("layer") or "furniture")
            item["default_position"] = deepcopy(item["position"])
            item["default_footprint"] = deepcopy(item["footprint"])
            result[furniture_id] = item
        return result

    def _read(self, conn: sqlite3.Connection) -> tuple[dict[str, Any], int]:
        row = conn.execute("SELECT revision,state_json FROM room_state WHERE id=1").fetchone()
        if row is None:
            raise RuntimeError("room_not_initialized")
        return json.loads(row["state_json"]), int(row["revision"])

    def _write(
        self,
        conn: sqlite3.Connection,
        state: dict[str, Any],
        previous_revision: int,
        kind: str,
        payload: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> int:
        revision = previous_revision + 1
        stamp = iso(now)
        conn.execute(
            "UPDATE room_state SET revision=?,state_json=?,updated_at=? WHERE id=1",
            (revision, self._dump(state), stamp),
        )
        self._event(conn, revision, kind, payload, now=now)
        return revision

    def _event(
        self,
        conn: sqlite3.Connection,
        revision: int,
        kind: str,
        payload: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> None:
        conn.execute(
            "INSERT INTO room_events(revision,kind,payload_json,created_at) VALUES(?,?,?,?)",
            (revision, kind, self._dump(payload), iso(now)),
        )

    def _blocked_tiles(self, state: dict[str, Any]) -> set[int]:
        result = set(self.wall_tiles)
        for furniture in state["furniture"].values():
            if furniture.get("blocking") is False:
                continue
            footprint = furniture["footprint"]
            for y in range(int(footprint["y"]), int(footprint["y"]) + int(footprint["height"])):
                for x in range(int(footprint["x"]), int(footprint["x"]) + int(footprint["width"])):
                    if 0 <= x < self.map_width and 0 <= y < self.map_height:
                        result.add(y * self.map_width + x)
        return result

    def _walkable(self, state: dict[str, Any], x: int, y: int) -> bool:
        return (
            0 <= x < self.map_width
            and 0 <= y < self.map_height
            and y * self.map_width + x not in self._blocked_tiles(state)
        )

    def _find_path(
        self,
        state: dict[str, Any],
        start: dict[str, int],
        target: dict[str, int],
    ) -> list[dict[str, int]]:
        return self._find_path_to_any(state, start, [target])

    def _find_path_to_any(
        self,
        state: dict[str, Any],
        start: dict[str, int],
        targets: list[dict[str, int]],
    ) -> list[dict[str, int]]:
        start_pair = (int(start["x"]), int(start["y"]))
        target_pairs = {(int(target["x"]), int(target["y"])) for target in targets}
        if start_pair in target_pairs:
            return [{"x": start_pair[0], "y": start_pair[1]}]
        blocked = self._blocked_tiles(state)
        target_pairs = {
            pair for pair in target_pairs
            if 0 <= pair[0] < self.map_width
            and 0 <= pair[1] < self.map_height
            and pair[1] * self.map_width + pair[0] not in blocked
        }
        if not target_pairs:
            return []
        queue = deque([start_pair])
        parents: dict[tuple[int, int], tuple[int, int] | None] = {start_pair: None}
        found: tuple[int, int] | None = None
        while queue:
            current = queue.popleft()
            if current in target_pairs:
                found = current
                break
            for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
                nxt = (current[0] + dx, current[1] + dy)
                if (
                    nxt in parents
                    or not 0 <= nxt[0] < self.map_width
                    or not 0 <= nxt[1] < self.map_height
                    or nxt[1] * self.map_width + nxt[0] in blocked
                ):
                    continue
                parents[nxt] = current
                queue.append(nxt)
        if found is None:
            return []
        pairs: list[tuple[int, int]] = []
        cursor: tuple[int, int] | None = found
        while cursor is not None:
            pairs.append(cursor)
            cursor = parents[cursor]
        return [{"x": x, "y": y} for x, y in reversed(pairs)]

    def _effective_position(self, character: dict[str, Any], now: datetime) -> dict[str, int]:
        movement = character.get("movement")
        if not movement:
            return deepcopy(character["position"])
        started = datetime.fromisoformat(movement["started_at"])
        elapsed = max(0.0, (now - started).total_seconds())
        index = min(len(movement["path"]) - 1, int(elapsed / self.step_seconds))
        return deepcopy(movement["path"][index])

    def _movement_finished(self, movement: dict[str, Any], now: datetime) -> bool:
        return now >= datetime.fromisoformat(movement["ends_at"])

    def _clear_action(self, character: dict[str, Any], *, now: datetime) -> None:
        character["activity"] = "idle"
        character["base_activity"] = "idle"
        character["active_furniture_id"] = None
        character["interaction"] = None
        character["slot_id"] = None
        character["together_with"] = None
        character["movement"] = None
        character["updated_at"] = iso(now)

    def _reconcile_together(self, state: dict[str, Any]) -> None:
        characters = state["characters"]
        for character in characters.values():
            character["together_with"] = None
            if character.get("movement"):
                character["activity"] = "moving"
            elif character.get("interaction"):
                character["activity"] = INTERACTION_ACTIVITIES[character["interaction"]]
                character["base_activity"] = character["activity"]
            else:
                character["activity"] = "idle"
                character["base_activity"] = "idle"
        owner, companion = characters["owner"], characters["companion"]
        if (
            not owner.get("movement")
            and not companion.get("movement")
            and owner.get("active_furniture_id")
            and owner.get("active_furniture_id") == companion.get("active_furniture_id")
            and owner.get("interaction") == companion.get("interaction")
            and owner.get("interaction") in TOGETHER_INTERACTIONS
        ):
            together_activity = f"{owner['interaction']}_together"
            owner["activity"] = together_activity
            companion["activity"] = together_activity
            owner["together_with"] = "companion"
            companion["together_with"] = "owner"

    def _occupied_slots(self, state: dict[str, Any], *, excluding: str = "") -> set[tuple[str, str]]:
        result: set[tuple[str, str]] = set()
        for character_id, character in state["characters"].items():
            if character_id == excluding:
                continue
            furniture_id = character.get("active_furniture_id")
            slot_id = character.get("slot_id")
            movement = character.get("movement") or {}
            pending = movement.get("pending") or {}
            furniture_id = furniture_id or pending.get("furniture_id")
            slot_id = slot_id or pending.get("slot_id")
            if furniture_id and slot_id:
                result.add((furniture_id, slot_id))
        return result

    def _select_slot(
        self,
        state: dict[str, Any],
        actor_id: str,
        furniture: dict[str, Any],
        interaction: str,
    ) -> dict[str, Any] | None:
        slots = furniture.get("interactionSlots", {}).get(interaction) or []
        if not slots:
            return {"id": interaction, "anchor": furniture.get("actionAnchors", {}).get(interaction)}
        occupied = self._occupied_slots(state, excluding=actor_id)
        available = []
        for slot in slots:
            allowed = slot.get("actorIds")
            if allowed and actor_id not in allowed:
                continue
            if (furniture["id"], slot["id"]) in occupied:
                continue
            available.append(slot)
        actor = state["characters"][actor_id]
        available.sort(
            key=lambda slot: abs(
                int(furniture["position"]["x"]) + int(slot["anchor"]["x"])
                - int(actor["position"]["x"]) * self.tile_size
            ) + abs(
                int(furniture["position"]["y"]) + int(slot["anchor"]["y"])
                - int(actor["position"]["y"]) * self.tile_size
            )
        )
        return deepcopy(available[0]) if available else None

    def _approach_path(
        self,
        state: dict[str, Any],
        actor_id: str,
        furniture: dict[str, Any],
    ) -> list[dict[str, int]]:
        footprint = furniture["footprint"]
        x, y = int(footprint["x"]), int(footprint["y"])
        width, height = int(footprint["width"]), int(footprint["height"])
        candidates: list[dict[str, int]] = []
        for tile_x in range(x - 1, x + width + 1):
            candidates.extend(({"x": tile_x, "y": y - 1}, {"x": tile_x, "y": y + height}))
        for tile_y in range(y, y + height):
            candidates.extend(({"x": x - 1, "y": tile_y}, {"x": x + width, "y": tile_y}))
        start = state["characters"][actor_id]["position"]
        return self._find_path_to_any(state, start, candidates)

    def _direction_for_path(self, path: list[dict[str, int]], fallback: str) -> str:
        if len(path) < 2:
            return fallback
        dx = path[-1]["x"] - path[-2]["x"]
        dy = path[-1]["y"] - path[-2]["y"]
        if abs(dx) > abs(dy):
            return "right" if dx > 0 else "left"
        return "down" if dy > 0 else "up"

    def _start_movement(
        self,
        character: dict[str, Any],
        path: list[dict[str, int]],
        *,
        now: datetime,
        pending: dict[str, Any] | None = None,
    ) -> None:
        duration = max(0, len(path) - 1) * self.step_seconds
        character["movement"] = {
            "path": deepcopy(path),
            "target": deepcopy(path[-1]),
            "started_at": iso(now),
            "ends_at": iso(now + timedelta(seconds=duration)),
            "pending": deepcopy(pending),
        }
        character["activity"] = "moving"
        character["base_activity"] = "moving"
        character["active_furniture_id"] = None
        character["interaction"] = None
        character["slot_id"] = None
        character["together_with"] = None
        character["direction"] = self._direction_for_path(path, character["direction"])
        character["updated_at"] = iso(now)

    def _finish_character_movement(
        self,
        state: dict[str, Any],
        character: dict[str, Any],
        *,
        now: datetime,
    ) -> None:
        movement = character.get("movement") or {}
        path = movement.get("path") or [character["position"]]
        pending = movement.get("pending") or None
        character["position"] = deepcopy(path[-1])
        character["movement"] = None
        if pending and pending.get("kind") == "use":
            character["active_furniture_id"] = pending["furniture_id"]
            character["interaction"] = pending["interaction"]
            character["slot_id"] = pending.get("slot_id")
            if pending.get("facing"):
                character["direction"] = pending["facing"]
            furniture = state["furniture"][pending["furniture_id"]]
            if pending["interaction"] == "toggle_tv":
                furniture["textureState"] = "off" if furniture.get("textureState") == "on" else "on"
        else:
            character["active_furniture_id"] = None
            character["interaction"] = None
            character["slot_id"] = None
        character["updated_at"] = iso(now)

    def _advance(self, state: dict[str, Any], now: datetime) -> list[str]:
        completed: list[str] = []
        for character_id, character in state["characters"].items():
            movement = character.get("movement")
            if movement and self._movement_finished(movement, now):
                self._finish_character_movement(state, character, now=now)
                completed.append(character_id)
        if completed:
            self._reconcile_together(state)
        return completed

    def _snapshot_payload(
        self,
        state: dict[str, Any],
        revision: int,
        *,
        now: datetime,
        detail: str,
        scope: str,
    ) -> dict[str, Any]:
        characters = []
        for character in state["characters"].values():
            item = deepcopy(character)
            item["position"] = self._effective_position(character, now)
            movement = item.get("movement")
            if movement:
                started = datetime.fromisoformat(movement["started_at"])
                ends = datetime.fromisoformat(movement["ends_at"])
                total = max(0.001, (ends - started).total_seconds())
                movement["progress"] = min(1.0, max(0.0, (now - started).total_seconds() / total))
            characters.append(item)
        payload: dict[str, Any] = {
            "contract_version": state["contract_version"],
            "revision": revision,
            "scene": deepcopy(state["scene"]),
            "characters": characters,
            "recent_events": self.events_after(max(0, self.latest_event_id() - 10), limit=10),
            "event_cursor": self.latest_event_id(),
        }
        if scope in {"all", "room"}:
            furniture = []
            for item in state["furniture"].values():
                public_item = self._public_furniture(item)
                occupants = []
                for character in state["characters"].values():
                    movement = character.get("movement") or {}
                    pending = movement.get("pending") or {}
                    active_furniture_id = character.get("active_furniture_id")
                    reserved_furniture_id = pending.get("furniture_id") if pending.get("kind") == "use" else None
                    if item["id"] not in {active_furniture_id, reserved_furniture_id}:
                        continue
                    occupants.append({
                        "character_id": character["id"],
                        "interaction": character.get("interaction") or pending.get("interaction"),
                        "slot_id": character.get("slot_id") or pending.get("slot_id"),
                    })
                public_item["occupants"] = occupants
                furniture.append(public_item)
            payload["furniture"] = furniture
        if detail == "full" and scope in {"all", "room"}:
            payload["semantic_map"] = self._semantic_map(state)
        return payload

    @staticmethod
    def _public_furniture(item: dict[str, Any]) -> dict[str, Any]:
        keep = (
            "id", "runtime_id", "asset", "position", "footprint", "blocking",
            "semantic_role", "interactions", "textureState", "interactionSlots",
        )
        return {key: deepcopy(item[key]) for key in keep if key in item}

    def _semantic_map(self, state: dict[str, Any]) -> dict[str, Any]:
        regions = []
        for item in state["furniture"].values():
            footprint = item["footprint"]
            tiles = []
            for y in range(int(footprint["y"]), int(footprint["y"]) + int(footprint["height"])):
                for x in range(int(footprint["x"]), int(footprint["x"]) + int(footprint["width"])):
                    if 0 <= x < self.map_width and 0 <= y < self.map_height:
                        tiles.append(y * self.map_width + x)
            regions.append({
                "id": item["id"],
                "role": item["semantic_role"],
                "blocking": item.get("blocking") is not False,
                "tiles": tiles,
            })
        return {
            "width": self.map_width,
            "height": self.map_height,
            "tile_size": self.tile_size,
            "encoding": "flat-tile-index-masks",
            "regions": regions,
            "wall_tiles": sorted(self.wall_tiles),
        }

    def snapshot(
        self,
        *,
        scope: str = "all",
        detail: str = "summary",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if scope not in {"all", "room", "characters"}:
            raise ValueError("invalid_scope")
        if detail not in {"summary", "full"}:
            raise ValueError("invalid_detail")
        current = now or utc_now()
        with self._lock, closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            state, revision = self._read(conn)
            completed = self._advance(state, current)
            if completed:
                revision = self._write(
                    conn,
                    state,
                    revision,
                    "character_transition_completed",
                    {"character_ids": completed},
                    now=current,
                )
            conn.commit()
        return self._snapshot_payload(state, revision, now=current, detail=detail, scope=scope)

    def move(
        self,
        actor_id: str,
        target: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if actor_id not in CHARACTER_IDS:
            raise ValueError("invalid_actor")
        current = now or utc_now()
        with self._lock, closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            state, revision = self._read(conn)
            self._advance(state, current)
            character = state["characters"][actor_id]
            character["position"] = self._effective_position(character, current)
            self._clear_action(character, now=current)
            kind = str(target.get("kind") or "tile")
            if kind == "tile":
                destination = {"x": int(target["x"]), "y": int(target["y"])}
                path = self._find_path(state, character["position"], destination)
            elif kind == "furniture":
                furniture_id = canonical_furniture_id(str(target.get("furniture_id") or target.get("id") or ""))
                furniture = state["furniture"].get(furniture_id)
                if not furniture:
                    raise KeyError("furniture_not_found")
                path = self._approach_path(state, actor_id, furniture)
            elif kind == "character":
                other_id = str(target.get("character_id") or target.get("id") or "")
                other = state["characters"].get(other_id)
                if not other:
                    raise KeyError("character_not_found")
                destination = self._effective_position(other, current)
                candidates = [
                    {"x": destination["x"] + dx, "y": destination["y"] + dy}
                    for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1))
                ]
                path = self._find_path_to_any(state, character["position"], candidates)
            else:
                raise ValueError("invalid_target_kind")
            if not path:
                raise ValueError("target_unreachable")
            self._start_movement(character, path, now=current)
            self._reconcile_together(state)
            revision = self._write(
                conn,
                state,
                revision,
                "character_move_started",
                {"character_id": actor_id, "target": path[-1], "path_length": len(path)},
                now=current,
            )
            conn.commit()
        return self._snapshot_payload(state, revision, now=current, detail="summary", scope="all")

    def use_furniture(
        self,
        actor_id: str,
        furniture_id: str,
        interaction: str = "",
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if actor_id not in CHARACTER_IDS:
            raise ValueError("invalid_actor")
        current = now or utc_now()
        canonical_id = canonical_furniture_id(furniture_id)
        with self._lock, closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            state, revision = self._read(conn)
            self._advance(state, current)
            furniture = state["furniture"].get(canonical_id)
            if not furniture:
                raise KeyError("furniture_not_found")
            interactions = list(furniture.get("interactions") or [])
            chosen = str(interaction or (interactions[0] if len(interactions) == 1 else ""))
            if chosen not in interactions:
                raise ValueError("interaction_not_supported")
            character = state["characters"][actor_id]
            character["position"] = self._effective_position(character, current)
            self._clear_action(character, now=current)
            slot = self._select_slot(state, actor_id, furniture, chosen)
            if slot is None:
                raise ValueError("furniture_no_available_slot")
            path = self._approach_path(state, actor_id, furniture)
            if not path:
                raise ValueError("furniture_unreachable")
            pending = {
                "kind": "use",
                "furniture_id": canonical_id,
                "interaction": chosen,
                "slot_id": slot.get("id"),
                "facing": slot.get("facing"),
            }
            if len(path) == 1:
                self._start_movement(character, path, now=current, pending=pending)
                self._finish_character_movement(state, character, now=current)
            else:
                self._start_movement(character, path, now=current, pending=pending)
            self._reconcile_together(state)
            revision = self._write(
                conn,
                state,
                revision,
                "furniture_use_started",
                {
                    "character_id": actor_id,
                    "furniture_id": canonical_id,
                    "interaction": chosen,
                    "slot_id": slot.get("id"),
                },
                now=current,
            )
            conn.commit()
        return self._snapshot_payload(state, revision, now=current, detail="summary", scope="all")

    def stop(self, actor_id: str, *, now: datetime | None = None) -> dict[str, Any]:
        if actor_id not in CHARACTER_IDS:
            raise ValueError("invalid_actor")
        current = now or utc_now()
        with self._lock, closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            state, revision = self._read(conn)
            character = state["characters"][actor_id]
            character["position"] = self._effective_position(character, current)
            self._clear_action(character, now=current)
            self._reconcile_together(state)
            revision = self._write(
                conn,
                state,
                revision,
                "character_stopped",
                {"character_id": actor_id},
                now=current,
            )
            conn.commit()
        return self._snapshot_payload(state, revision, now=current, detail="summary", scope="all")

    def update_layout(
        self,
        positions: dict[str, dict[str, Any]],
        *,
        actor_id: str = "owner",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if actor_id != "owner":
            raise ValueError("layout_owner_must_be_owner")
        current = now or utc_now()
        with self._lock, closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            state, revision = self._read(conn)
            candidate = deepcopy(state["furniture"])
            for supplied_id, position in positions.items():
                furniture_id = canonical_furniture_id(supplied_id)
                item = candidate.get(furniture_id)
                if not item:
                    raise KeyError("furniture_not_found")
                x, y = int(position["x"]), int(position["y"])
                if not 0 <= x <= 1600 or not 0 <= y <= 1600:
                    raise ValueError("layout_position_out_of_bounds")
                default_position = item["default_position"]
                default_footprint = item["default_footprint"]
                item["position"] = {"x": x, "y": y}
                item["footprint"] = {
                    **default_footprint,
                    "x": int(default_footprint["x"]) + round((x - int(default_position["x"])) / self.tile_size),
                    "y": int(default_footprint["y"]) + round((y - int(default_position["y"])) / self.tile_size),
                }
            blocking: set[int] = set(self.wall_tiles)
            for item in candidate.values():
                if item.get("blocking") is False:
                    continue
                footprint = item["footprint"]
                tiles = {
                    tile_y * self.map_width + tile_x
                    for tile_y in range(int(footprint["y"]), int(footprint["y"]) + int(footprint["height"]))
                    for tile_x in range(int(footprint["x"]), int(footprint["x"]) + int(footprint["width"]))
                    if 0 <= tile_x < self.map_width and 0 <= tile_y < self.map_height
                }
                expected = int(footprint["width"]) * int(footprint["height"])
                if len(tiles) != expected or tiles & blocking:
                    raise ValueError("layout_collision")
                blocking.update(tiles)
            state["furniture"] = candidate
            for character in state["characters"].values():
                self._clear_action(character, now=current)
            revision = self._write(
                conn,
                state,
                revision,
                "layout_changed",
                {"actor_id": actor_id, "furniture_ids": sorted(canonical_furniture_id(key) for key in positions)},
                now=current,
            )
            conn.commit()
        return self._snapshot_payload(state, revision, now=current, detail="summary", scope="all")

    def apply_moods(
        self,
        moods: dict[str, dict[str, Any]],
        *,
        now: datetime | None = None,
    ) -> bool:
        current = now or utc_now()
        with self._lock, closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            state, revision = self._read(conn)
            changed = []
            for character_id, mood in moods.items():
                if character_id not in state["characters"]:
                    continue
                previous = state["characters"][character_id].get("mood") or {}
                if (
                    previous.get("code") == mood.get("code")
                    and previous.get("label") == mood.get("label")
                    and int(previous.get("revision") or 0) == int(mood.get("revision") or 0)
                ):
                    continue
                state["characters"][character_id]["mood"] = deepcopy(mood)
                changed.append(character_id)
            if changed:
                self._write(
                    conn,
                    state,
                    revision,
                    "character_moods_updated",
                    {"character_ids": changed},
                    now=current,
                )
            conn.commit()
        return bool(changed)

    def latest_event_id(self) -> int:
        with closing(self._connect()) as conn:
            return int(conn.execute("SELECT COALESCE(MAX(id),0) FROM room_events").fetchone()[0])

    def events_after(self, cursor: int, *, limit: int = 100) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM room_events WHERE id>? ORDER BY id LIMIT ?",
                (max(0, int(cursor)), min(500, max(1, int(limit)))),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "revision": int(row["revision"]),
                "type": row["kind"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
