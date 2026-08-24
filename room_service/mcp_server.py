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
            description=(
                "Read the shared Room scene, both character states, furniture occupancy, "
                "recent activity events and revision. Use detail=full only when the semantic map is needed."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["all", "room", "characters"], "default": "all"},
                    "detail": {"type": "string", "enum": ["summary", "full"], "default": "summary"},
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
            description=(
                "Have the companion use any interactive furniture through one generic action. "
                "The Room chooses an allowed free slot, finds a path, and enters a together-state when the owner matches."
            ),
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


def execute_tool(store: RoomStore, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if name == "room_get_state":
        return store.snapshot(
            scope=str(args.get("scope") or "all"),
            detail=str(args.get("detail") or "summary"),
        ), False
    if name == "room_move":
        return store.move("companion", dict(args.get("target") or {})), False
    if name == "room_use_furniture":
        return store.use_furniture(
            "companion",
            str(args.get("furniture_id") or ""),
            str(args.get("interaction") or ""),
        ), False
    if name == "room_stop":
        return store.stop("companion"), False
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
