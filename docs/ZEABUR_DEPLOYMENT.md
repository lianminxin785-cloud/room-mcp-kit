# Zeabur deployment

This adapter runs the Room web UI, owner REST routes and companion MCP endpoint
in one container. Both control paths share one SQLite database.

## Required environment variable

Set `ROOM_TOKEN` to a random value containing at least 16 characters. The same
secret protects the web room and MCP endpoint.

`ROOM_DB` defaults to `/data/room.db` in the Docker image.

## Persistent storage

Mount a persistent volume at `/data`. Without a volume, room state and saved
layout can be lost when the service is redeployed.

## URLs

After binding an HTTPS domain, replace `ROOM_TOKEN` below with the configured
secret:

- Room: `https://YOUR_DOMAIN/?token=ROOM_TOKEN`
- MCP: `https://YOUR_DOMAIN/mcp?token=ROOM_TOKEN`
- Health check: `https://YOUR_DOMAIN/healthz`

Opening the Room URL once stores the token in a secure, HTTP-only browser
cookie and redirects to the clean root URL. MCP clients may alternatively send
the token in `Authorization: Bearer ROOM_TOKEN`.

Treat URLs containing the token as secrets. Do not paste them into public
issues, commits, screenshots or logs.
