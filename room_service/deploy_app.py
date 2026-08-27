from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
from http.cookies import SimpleCookie
from urllib.parse import parse_qsl, urlencode

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .app import create_app as create_room_app
from .config import ROOT, RoomSettings
from .core import RoomStore
from .mcp_server import create_server


COOKIE_NAME = "room_access"


def _provided_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    query_token = request.query_params.get("token", "")
    if query_token:
        return query_token
    cookie = SimpleCookie(request.headers.get("cookie", ""))
    morsel = cookie.get(COOKIE_NAME)
    return morsel.value if morsel else ""


def create_deploy_app(settings: RoomSettings | None = None) -> FastAPI:
    settings = (settings or RoomSettings.from_env()).validate()
    store = RoomStore(
        settings.db_path,
        initial_state_path=settings.initial_state_path,
        map_path=settings.map_path,
    )
    room_app = create_room_app(settings, store=store)
    mcp_server = create_server(store)
    mcp_app = mcp_server.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        host="0.0.0.0",
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        store.initialize()
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

    app = FastAPI(title="Room MCP Kit deployed", lifespan=lifespan)

    @app.middleware("http")
    async def protect_room(request: Request, call_next):
        if request.url.path == "/healthz":
            return await call_next(request)

        supplied = _provided_token(request)
        if not hmac.compare_digest(supplied, settings.token):
            return JSONResponse(
                {"detail": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        is_mcp = request.url.path == "/mcp" or request.url.path.startswith("/mcp/")
        if request.query_params.get("token") and not is_mcp:
            query = [(key, value) for key, value in parse_qsl(request.url.query) if key != "token"]
            target = request.url.path
            if query:
                target += "?" + urlencode(query)
            response = RedirectResponse(target, status_code=303)
            response.set_cookie(
                COOKIE_NAME,
                settings.token,
                httponly=True,
                secure=True,
                samesite="strict",
                max_age=60 * 60 * 24 * 30,
            )
            return response

        if request.url.path.startswith("/api/v1/room/"):
            headers = list(request.scope["headers"])
            headers.append((b"x-room-token", settings.token.encode("utf-8")))
            request.scope["headers"] = headers

        return await call_next(request)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    app.mount("/mcp", mcp_app, name="mcp")
    app.include_router(room_app.router)
    app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
    return app
