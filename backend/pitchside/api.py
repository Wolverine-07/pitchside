"""HTTP and WebSocket API.

    uv run uvicorn pitchside.api:app --reload

WS   /ws/match      live stream: events, stat snapshots, overlays, agent traces
GET  /api/overlays  the full overlay timeline for a match (for replays and renderers)
GET  /api/health    provider and version
     /mcp           the stats tools as an MCP server, bound to the latest live match
"""

from __future__ import annotations

import contextlib
import os
import uuid
from pathlib import Path

from agent_framework import MCPStreamableHTTPTool
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings

from pitchside import speech, telemetry
from pitchside.agents.llm import clients, config
from pitchside.runner import Broadcast
from pitchside.sim.engine import STORYLINES, simulate
from pitchside.sim.league import FIXTURES, LeagueState, clubs, matchday
from pitchside.stats.state import MatchState
from pitchside.tools import MATCH_HEADER, build_mcp_server

telemetry.setup()

LIVE: dict[str, MatchState] = {}


def latest_state(key: str | None = None) -> MatchState:
    if key and key in LIVE:
        return LIVE[key]
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
        "tracing": telemetry._done,
        "speech": speech.enabled(),
        "storylines": sorted(STORYLINES),
    }


@app.get("/api/speak")
async def speak(text: str, lang: str = "en") -> Response:
    """A caption read aloud by an Azure AI Speech neural voice (English, Hindi or Spanish)."""
    if not speech.enabled():
        return Response(status_code=503)
    try:
        audio = await run_in_threadpool(speech.synthesize, text, lang)
    except Exception:  # noqa: BLE001 - the browser falls back to its own voice
        return Response(status_code=502)
    return Response(
        audio, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"}
    )


@app.get("/api/meta")
def match_meta(seed: int = 16, storyline: str = "comeback") -> dict:
    """Clubs, rosters, venue and the league going into the matchday, so viewers can choose before kick-off."""
    meta = simulate(seed, storyline)[0]["data"]
    meta["league"] = league_for([]).snapshot()
    meta["fixtures"] = [{"home": h, "away": a} for h, a in FIXTURES]
    return meta


def league_for(fixtures) -> LeagueState:
    all_clubs = clubs()
    return LeagueState(
        fixtures,
        {c: k.name for c, k in all_clubs.items()},
        {c: k.colors[0] for c, k in all_clubs.items()},
    )


@contextlib.asynccontextmanager
async def broadcast(seed: int, storyline: str, profiles: list[str], langs: list[str]):
    """A Broadcast whose Analyst reads numbers over MCP, from this match only."""
    c = clients()
    key = uuid.uuid4().hex[:12]
    stats_mcp = MCPStreamableHTTPTool(
        name="pitchside-stats",
        url=f"http://127.0.0.1:{os.getenv('PORT', '8000')}/mcp/",
        static_headers={MATCH_HEADER: key},
    )
    fixtures = matchday(seed, storyline)
    b = Broadcast(
        fixtures[0].events,
        c["fast"],
        profiles,
        langs,
        deep_client=c["deep"],
        analyst_tools=[stats_mcp] if c["fast"] else None,
        league=league_for(fixtures),
    )
    LIVE[key] = b.state
    try:
        async with contextlib.AsyncExitStack() as stack:
            if c["fast"]:
                await stack.enter_async_context(stats_mcp)
            yield key, b
    finally:
        LIVE.pop(key, None)


@app.get("/api/overlays")
async def overlay_timeline(
    seed: int = 16, storyline: str = "comeback", profiles: str = "casual", langs: str = "en"
):
    async with broadcast(seed, storyline, _list(profiles, "casual"), _list(langs, "en")) as (_, b):
        return [item["overlay"] async for item in b.run() if item["kind"] == "overlay"]


@app.websocket("/ws/match")
async def live_match(ws: WebSocket) -> None:
    await ws.accept()
    q = ws.query_params
    seed, storyline = int(q.get("seed", 16)), q.get("storyline", "comeback")
    speed = float(q.get("speed", 10))
    profiles = _list(q.get("profiles"), "casual,analyst")
    langs = _list(q.get("langs"), "en")
    try:
        async with broadcast(seed, storyline, profiles, langs) as (key, b):
            await ws.send_json(
                {"kind": "hello", "match_key": key, "provider": config().provider, "meta": None}
            )
            async for item in b.run(speed=speed):
                await ws.send_json(item)
            await ws.send_json({"kind": "done"})
    except WebSocketDisconnect:
        pass


STATIC = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        file = STATIC / path
        return FileResponse(file if path and file.is_file() else STATIC / "index.html")
