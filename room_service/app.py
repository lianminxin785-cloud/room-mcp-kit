from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hmac
import json

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .config import RoomSettings
from .core import RoomStore


class MoveRequest(BaseModel):
    target: dict[str, object]


class UseRequest(BaseModel):
    furniture_id: str = Field(min_length=1, max_length=80)
    interaction: str = Field(default="", max_length=80)


class LayoutRequest(BaseModel):
    positions: dict[str, dict[str, int]]


def create_app(settings: RoomSettings | None = None, store: RoomStore | None = None) -> FastAPI:
    settings = (settings or RoomSettings.from_env()).validate()
    store = store or RoomStore(
        settings.db_path,
        initial_state_path=settings.initial_state_path,
        map_path=settings.map_path,
    )
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        store.initialize()
        yield

    app = FastAPI(title="Room MCP Kit", version="1", lifespan=lifespan)
    app.state.store = store

    def authenticate(x_room_token: str = Header(default="")) -> None:
        if not hmac.compare_digest(x_room_token, settings.token):
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/api/v1/room/health")
    async def health(_: None = Depends(authenticate)):
        return {
            "ok": True,
            "scene_id": store.scene_id,
            "revision": store.snapshot(scope="characters")["revision"],
            "event_cursor": store.latest_event_id(),
        }

    @app.get("/api/v1/room/state")
    async def state(
        scope: str = Query(default="all", pattern="^(all|room|characters)$"),
        detail: str = Query(default="summary", pattern="^(summary|full)$"),
        _: None = Depends(authenticate),
    ):
        return await asyncio.to_thread(store.snapshot, scope=scope, detail=detail)

    @app.post("/api/v1/room/characters/owner/move")
    async def owner_move(body: MoveRequest, _: None = Depends(authenticate)):
        try:
            return await asyncio.to_thread(store.move, "owner", body.target)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/room/characters/owner/use")
    async def owner_use(body: UseRequest, _: None = Depends(authenticate)):
        try:
            return await asyncio.to_thread(
                store.use_furniture,
                "owner",
                body.furniture_id,
                body.interaction,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/room/characters/owner/stop")
    async def owner_stop(_: None = Depends(authenticate)):
        return await asyncio.to_thread(store.stop, "owner")

    @app.put("/api/v1/room/layout")
    async def layout(body: LayoutRequest, _: None = Depends(authenticate)):
        try:
            return await asyncio.to_thread(store.update_layout, body.positions)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/v1/room/events")
    async def events(
        after: int = Query(default=0, ge=0),
        _: None = Depends(authenticate),
    ):
        async def stream():
            cursor = after
            quiet = 0
            while True:
                await asyncio.to_thread(store.snapshot, scope="characters")
                rows = await asyncio.to_thread(store.events_after, cursor)
                if rows:
                    for event in rows:
                        cursor = event["id"]
                        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                        yield f"id: {cursor}\nevent: {event['type']}\ndata: {payload}\n\n"
                    quiet = 0
                else:
                    quiet += 1
                    if quiet >= 30:
                        yield ": keepalive\n\n"
                        quiet = 0
                await asyncio.sleep(0.5)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return app
