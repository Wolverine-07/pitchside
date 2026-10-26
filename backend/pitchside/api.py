"""HTTP and WebSocket API.

    uv run uvicorn pitchside.api:app --reload

WS   /ws/match      live stream: events, stat snapshots, overlays, agent traces
GET  /api/overlays  the full overlay timeline for a match (for replays and renderers)
GET  /api/health    provider and version
     /mcp           the stats tools as an MCP server, bound to the latest live match
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings

from pitchside.agents.llm import clients, config
from pitchside.runner import Broadcast
from pitchside.sim.engine import STORYLINES, simulate
from pitchside.stats.state import MatchState
from pitchside.tools import build_mcp_server

LIVE: dict[str, MatchState] = {}


def latest_state() -> MatchState:
    if not LIVE:
        # Nobody is watching yet: serve a finished demo match so MCP clients still get answers.
        st = MatchState()
        for e in simulate(16, "comeback"):
            st.ingest(e)
        LIVE["demo"] = st
    return next(reversed(LIVE.values()))


mcp = build_mcp_server(latest_state)
mcp_app = mcp.streamable_http_app(
    streamable_http_path="/",
    stateless_http=True,
    # Served behind Azure Container Apps ingress, so the Host header is the public name.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Pitchside", version="0.1.0", lifespan=lifespan)
app.mount("/mcp", mcp_app)


def _list(raw: str | None, default: str) -> list[str]:
    return [x.strip() for x in (raw or default).split(",") if x.strip()]


@app.get("/api/health")
def health() -> dict:
    cfg = config()
    return {
        "ok": True,
        "provider": cfg.provider,
        "model": cfg.model,
        "storylines": sorted(STORYLINES),
    }


@app.get("/api/overlays")
async def overlay_timeline(
    seed: int = 16, storyline: str = "comeback", profiles: str = "casual", langs: str = "en"
):
    c = clients()
    b = Broadcast(
        simulate(seed, storyline),
        c["fast"],
        _list(profiles, "casual"),
        _list(langs, "en"),
        deep_client=c["deep"],
    )
    return [item["overlay"] async for item in b.run() if item["kind"] == "overlay"]


@app.websocket("/ws/match")
async def live_match(ws: WebSocket) -> None:
    await ws.accept()
    q = ws.query_params
    seed, storyline = int(q.get("seed", 16)), q.get("storyline", "comeback")
    speed = float(q.get("speed", 10))
    c = clients()
    b = Broadcast(
        simulate(seed, storyline),
        c["fast"],
        _list(q.get("profiles"), "casual,analyst"),
        _list(q.get("langs"), "en"),
        deep_client=c["deep"],
    )
    key = f"{id(ws)}"
    LIVE[key] = b.state
    try:
        async for item in b.run(speed=speed):
            await ws.send_json(item)
        await ws.send_json({"kind": "done"})
    except WebSocketDisconnect:
        pass
    finally:
        LIVE.pop(key, None)


STATIC = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        file = STATIC / path
        return FileResponse(file if path and file.is_file() else STATIC / "index.html")
