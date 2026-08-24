from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import os
from pathlib import Path
import secrets
import sys
import threading
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
ROOM_PREFIX = "/api/v1/room"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from room_service.app import create_app as create_room_app
from room_service.config import RoomSettings


def room_proxy_allowed(path: str, method: str) -> bool:
    return (
        (method == "GET" and path in {"state", "events"})
        or (method == "POST" and path in {
            "characters/owner/move",
            "characters/owner/use",
            "characters/owner/stop",
        })
        or (method == "PUT" and path == "layout")
    )


def create_gateway_app(*, room_url: str, room_token: str) -> FastAPI:
    parsed = urlsplit(room_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("room_url must be a loopback HTTP URL")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.room_http = httpx.AsyncClient(
            base_url=room_url.rstrip("/"),
            headers={"X-Room-Token": room_token},
            timeout=httpx.Timeout(30),
        )
        try:
            yield
        finally:
            await app.state.room_http.aclose()

    app = FastAPI(title="Room MCP Kit local preview", lifespan=lifespan)

    @app.api_route(f"{ROOM_PREFIX}/{{room_path:path}}", methods=["GET", "POST", "PUT"])
    async def room_proxy(room_path: str, request: Request):
        clean_path = room_path.strip("/")
        if not room_proxy_allowed(clean_path, request.method):
            raise HTTPException(status_code=404, detail="room route not found")
        upstream_request = app.state.room_http.build_request(
            request.method,
            "/" + clean_path,
            params=list(request.query_params.multi_items()),
            content=await request.body(),
            headers={
                "Content-Type": request.headers["content-type"]
            } if request.headers.get("content-type") else None,
        )
        try:
            upstream = await app.state.room_http.send(
                upstream_request,
                stream=clean_path == "events",
            )
        except httpx.TransportError as exc:
            raise HTTPException(status_code=502, detail="room unavailable") from exc
        safe_headers = {
            key: value
            for key, value in upstream.headers.items()
            if key.lower() in {"content-type", "cache-control", "content-length", "x-accel-buffering"}
        }
        if clean_path == "events":
            return StreamingResponse(
                upstream.aiter_raw(),
                status_code=upstream.status_code,
                headers=safe_headers,
                background=BackgroundTask(upstream.aclose),
            )
        content = await upstream.aread()
        await upstream.aclose()
        return Response(content=content, status_code=upstream.status_code, headers=safe_headers)

    app.mount("/", StaticFiles(directory=WEB_ROOT, html=True), name="web")
    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Room REST and a same-origin local preview.")
    parser.add_argument("--port", type=int, default=8878, help="Same-origin preview port.")
    parser.add_argument("--room-port", type=int, default=18451, help="Internal Room REST port.")
    parser.add_argument(
        "--db",
        type=Path,
        default=ROOT / "room_service" / "data" / "room.db",
        help="Persistent local Room SQLite path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    room_token = os.environ.get("ROOM_TOKEN", "").strip() or secrets.token_urlsafe(24)
    settings = RoomSettings(
        token=room_token,
        db_path=args.db,
        initial_state_path=ROOT / "web" / "room" / "data" / "initial-state.json",
        map_path=ROOT / "web" / "room" / "data" / "room-map.json",
    ).validate()
    room_app = create_room_app(settings)
    room_thread = threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": room_app,
            "host": "127.0.0.1",
            "port": args.room_port,
            "access_log": False,
            "log_level": "warning",
        },
        daemon=True,
        name="room-rest-dev",
    )
    room_thread.start()
    gateway = create_gateway_app(
        room_url=f"http://127.0.0.1:{args.room_port}/api/v1/room",
        room_token=room_token,
    )
    print(f"Room shared preview: http://127.0.0.1:{args.port}/")
    print(f"Room state database: {args.db.resolve()}")
    uvicorn.run(
        gateway,
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
