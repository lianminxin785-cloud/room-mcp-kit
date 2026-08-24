from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import anyio
import mcp.types as types
from mcp.server.lowlevel import Server

from .config import ROOT
from .core import RoomStore


def tool_models() -> list[types.Tool]:
    return [
        types.Tool(
            name="room_get_state",
            description="Get compact Room state; request furniture, events or map only when needed.",
            input_schema={
                "type": "object",
                "properties": {
                    "include_furniture": {"type": "boolean", "default": False},
                    "include_map": {"type": "boolean", "default": False},
                    "include_recent_events": {"type": "boolean", "default": False},
                },
            },
        ),
        types.Tool(
            name="room_move",
            description=(
                "Move the companion character. Target one walkable tile, furniture semantic region, "
                "or the owner character. This tool cannot move the owner."
            ),
            input_schema={
                "type": "object",
                "required": ["target"],
                "properties": {
                    "target": {
                        "type": "object",
                        "required": ["kind"],
                        "properties": {
                            "kind": {"type": "string", "enum": ["tile", "furniture", "character"]},
                            "x": {"type": "integer", "minimum": 0, "maximum": 99},
                            "y": {"type": "integer", "minimum": 0, "maximum": 99},
                            "furniture_id": {"type": "string"},
                            "character_id": {"type": "string", "enum": ["owner"]},
                        },
                    }
                },
            },
        ),
        types.Tool(
            name="room_use_furniture",
            description="Use furniture directly; Room validates state, chooses a slot, and walks.",
            input_schema={
                "type": "object",
                "required": ["furniture_id"],
                "properties": {
                    "furniture_id": {"type": "string"},
                    "interaction": {"type": "string", "description": "Optional when the furniture has one interaction."},
                },
            },
        ),
        types.Tool(
            name="room_stop",
            description="Stop the companion, cancel pending movement/use, release the furniture slot and return to idle.",
            input_schema={"type": "object", "properties": {}},
        ),
    ]


def _character_summary(character: dict[str, Any]) -> dict[str, Any]:
    movement = character.get("movement") or {}
    pending = movement.get("pending") or {}
    furniture_id = character.get("active_furniture_id") or pending.get("furniture_id")
    action = character.get("interaction") or pending.get("interaction")
    slot_id = character.get("slot_id") or pending.get("slot_id")
    if movement:
        phase = "approaching" if pending else "moving"
        completion_at = movement.get("ends_at")
    elif furniture_id:
        phase = "completed"
        completion_at = None
    else:
        phase = "idle"
        completion_at = None
    return {
        "id": character.get("id"),
        "position": character.get("position"),
        "activity": character.get("activity"),
        "furniture": furniture_id,
        "action": action,
        "slot": slot_id,
        "phase": phase,
        "completion_at": completion_at,
    }


def _character(snapshot: dict[str, Any], actor_id: str = "companion") -> dict[str, Any]:
    return next(
        (item for item in snapshot.get("characters", []) if item.get("id") == actor_id),
        {},
    )


def _compact_state(snapshot: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "scene_id": (snapshot.get("scene") or {}).get("id"),
        "revision": snapshot.get("revision"),
        "event_cursor": snapshot.get("event_cursor"),
        "characters": [_character_summary(item) for item in snapshot.get("characters", [])],
    }
    if args.get("include_furniture") or args.get("include_map"):
        result["furniture"] = snapshot.get("furniture", [])
    if args.get("include_map"):
        result["semantic_map"] = snapshot.get("semantic_map")
    if args.get("include_recent_events"):
        result["recent_events"] = snapshot.get("recent_events", [])
    return result


def _move_receipt(snapshot: dict[str, Any]) -> dict[str, Any]:
    character = _character(snapshot)
    movement = character.get("movement") or {}
    path = movement.get("path") or []
    return {
        "ok": True,
        "actor": "companion",
        "target": path[-1] if path else character.get("position"),
        "phase": "moving" if movement else "completed",
        "completion_at": movement.get("ends_at"),
    }


def _furniture_receipt(snapshot: dict[str, Any]) -> dict[str, Any]:
    character = _character(snapshot)
    movement = character.get("movement") or {}
    pending = movement.get("pending") or {}
    return {
        "ok": True,
        "actor": "companion",
        "furniture": character.get("active_furniture_id") or pending.get("furniture_id"),
        "action": character.get("interaction") or pending.get("interaction"),
        "slot": character.get("slot_id") or pending.get("slot_id"),
        "phase": "approaching" if movement else "completed",
        "completion_at": movement.get("ends_at"),
    }


def execute_tool(store: RoomStore, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if name == "room_get_state":
        include_room = bool(args.get("include_furniture") or args.get("include_map"))
        snapshot = store.snapshot(
            scope="all" if include_room else "characters",
            detail="full" if args.get("include_map") else "summary",
        )
        return _compact_state(snapshot, args), False
    if name == "room_move":
        snapshot = store.move("companion", dict(args.get("target") or {}))
        return _move_receipt(snapshot), False
    if name == "room_use_furniture":
        snapshot = store.use_furniture(
            "companion",
            str(args.get("furniture_id") or ""),
            str(args.get("interaction") or ""),
        )
        return _furniture_receipt(snapshot), False
    if name == "room_stop":
        store.stop("companion")
        return {
            "ok": True,
            "actor": "companion",
            "activity": "idle",
            "phase": "completed",
        }, False
    return {"error": "unknown_tool"}, True


def create_server(store: RoomStore) -> Server:
    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tool_models())

    def text(value: Any, *, error: bool = False) -> types.CallToolResult:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(value, ensure_ascii=False, separators=(",", ":")))],
            is_error=error,
        )

    async def on_call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
        try:
            result, is_error = await anyio.to_thread.run_sync(
                execute_tool,
                store,
                params.name,
                dict(params.arguments or {}),
            )
            return text(result, error=is_error)
        except (KeyError, TypeError, ValueError) as exc:
            return text({"error": str(exc)}, error=True)

    return Server("room-mcp-kit", on_list_tools=on_list_tools, on_call_tool=on_call_tool)


def build_store() -> RoomStore:
    store = RoomStore(
        Path(os.environ.get("ROOM_DB", ROOT / "room_service" / "data" / "room.db")),
        initial_state_path=Path(
            os.environ.get("ROOM_INITIAL_STATE", ROOT / "web" / "room" / "data" / "initial-state.json")
        ),
        map_path=Path(os.environ.get("ROOM_MAP", ROOT / "web" / "room" / "data" / "room-map.json")),
    )
    store.initialize()
    return store


async def run_stdio(server: Server) -> None:
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser(description="Room MCP Kit server")
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "18452")))
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("Room MCP must remain loopback-only")
    store = build_store()
    server = create_server(store)
    if args.http or os.environ.get("MCP_TRANSPORT", "").lower() in {"http", "streamable-http"}:
        import uvicorn
        app = server.streamable_http_app(
            streamable_http_path="/mcp",
            json_response=True,
            stateless_http=True,
            host=args.host,
        )
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        anyio.run(run_stdio, server)


if __name__ == "__main__":
    main()
