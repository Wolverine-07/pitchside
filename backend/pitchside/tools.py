"""Stats tools: the only way agents get numbers.

One set of functions, published two ways:
- as an MCP server (mounted on the API at /mcp), which is what the deployed
  agents use and what any MCP client, such as GitHub Copilot in VS Code, can
  connect to;
- as in-process Agent Framework tools, for offline runs and evaluations.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable

from agent_framework import FunctionTool, tool
from mcp.server import MCPServer
from mcp.server.mcpserver import Context

from pitchside.stats.state import MatchState

WINDOWS = (60, 90, 180, 300, 600)


class StatsTools:
    def __init__(self, state: MatchState) -> None:
        self.state = state
        self.seen: list = []  # every result handed to an agent, so the Verifier can accept exactly those

    def match_snapshot(self) -> dict:
        """Score, minute, possession, momentum (-100 away on top .. +100 home on top), 5-minute chaos index and xG."""
        return self.state.snapshot()

    def team_metrics(self, team: str, window_s: int | None = None) -> dict:
        """Possession, passing, pass accuracy under pressure, pass difficulty, shots, xG, regains, PPDA and tempo
        for one team (3-letter code). window_s limits to the last N seconds of play; omit for the whole match."""
        return self.state.team_metrics(team.upper(), window_s)

    def player_summary(self, player_id: str) -> dict:
        """Passes, pass accuracy, shots, xG, goals, assists, regains, distance covered and top speed for a player.
        Takes an id like KSC-09 or a name like 'Wexavi'."""
        return self.state.player_summary(self.resolve_player(player_id))

    def resolve_player(self, key: str) -> str:
        key = key.strip()
        if key.upper() in self.state.names:
            return key.upper()
        low = key.lower()
        for pid, name in self.state.names.items():
            if low == name.lower() or low == name.split()[-1].lower():
                return pid
        return key.upper()

    def chaos_index(self, window_s: int = 300) -> dict:
        """Control (0) vs chaos (1) over the last window_s seconds, from turnovers, possession length and duels."""
        return {"chaos_index": self.state.chaos(window_s), "window_s": window_s}

    def recent_moments(self, limit: int = 5) -> list[dict]:
        """The most recent moments the stats engine flagged, newest last, with their evidence."""
        return [m.to_dict() for m in self.state.moments[-limit:]]

    def roster(self, team: str) -> list[dict]:
        """Player ids, names, numbers and roles for a team (3-letter code)."""
        side = "home" if self.state.meta["home"]["code"] == team.upper() else "away"
        return self.state.meta[side]["players"]

    def league_table(self) -> dict:
        """Live Coastal League table (as it stands, with this matchday's scores) and the other matchday scores."""
        lg = getattr(self.state, "league", None)
        if lg is None:
            return {"note": "no league context for this match"}
        snap = lg.snapshot()
        return {
            "table": [
                {k: r[k] for k in ("pos", "code", "name", "points", "gd", "played", "moved")}
                for r in snap["table"]
            ],
            "scores": snap["scores"],
        }

    def functions(self) -> list[Callable]:
        return [
            self.league_table,
            self.match_snapshot,
            self.team_metrics,
            self.player_summary,
            self.chaos_index,
            self.recent_moments,
            self.roster,
        ]

    def agent_tools(self) -> list[FunctionTool]:
        return [tool(self._recorded(f)) for f in self.functions()]

    def _recorded(self, f: Callable) -> Callable:
        @functools.wraps(f)
        def call(*args, **kwargs):
            result = f(*args, **kwargs)
            self.seen.append(result)
            return result

        return call

    def fact_sheet(self, players: list[str]) -> dict:
        """Everything the Verifier will accept as true right now."""
        teams = self.state.teams
        return {
            "snapshot": self.match_snapshot(),
            "metrics": {t: {w: self.team_metrics(t, w) for w in (*WINDOWS, None)} for t in teams},
            "chaos": {w: self.state.chaos(w) for w in WINDOWS},
            "players": {p: self.player_summary(p) for p in players},
            "league": {
                r["code"]: {"live_position": r["pos"], "points": r["points"], "gd": r["gd"]}
                for r in (self.league_table().get("table") or [])
            },
        }


MATCH_HEADER = "x-pitchside-match"


def _match_key(ctx: Context | None) -> str | None:
    try:
        return ctx.request_context.request.headers.get(MATCH_HEADER)
    except Exception:  # noqa: BLE001 - stdio clients have no HTTP request
        return None


def build_mcp_server(get_state: Callable[[str | None], MatchState]) -> MCPServer:
    """MCP server over live matches. get_state(key) returns the MatchState for the
    x-pitchside-match header, or the latest match when the header is missing."""
    server = MCPServer(
        name="pitchside-stats",
        instructions="Live statistics for the current synthetic match. Every number Pitchside shows comes from here.",
    )

    def _tools(ctx: Context | None) -> StatsTools:
        return StatsTools(get_state(_match_key(ctx)))

    @server.tool()
    def match_snapshot(ctx: Context | None = None) -> str:
        """Score, minute, possession, momentum, chaos index and xG for the live match."""
        return json.dumps(_tools(ctx).match_snapshot())

    @server.tool()
    def team_metrics(team: str, window_s: int | None = None, ctx: Context | None = None) -> str:
        """Team metrics (possession, passing, pressure, xG, regains, PPDA, tempo). window_s = last N seconds."""
        return json.dumps(_tools(ctx).team_metrics(team, window_s))

    @server.tool()
    def player_summary(player_id: str, ctx: Context | None = None) -> str:
        """Player stats for an id like KSC-09."""
        return json.dumps(_tools(ctx).player_summary(player_id))

    @server.tool()
    def chaos_index(window_s: int = 300, ctx: Context | None = None) -> str:
        """Control (0) vs chaos (1) over the last window_s seconds."""
        return json.dumps(_tools(ctx).chaos_index(window_s))

    @server.tool()
    def recent_moments(limit: int = 5, ctx: Context | None = None) -> str:
        """Most recent flagged moments with their evidence."""
        return json.dumps(_tools(ctx).recent_moments(limit))

    @server.tool()
    def league_table(ctx: Context | None = None) -> str:
        """Live league table and the other matchday scores."""
        return json.dumps(_tools(ctx).league_table())

    @server.tool()
    def roster(team: str, ctx: Context | None = None) -> str:
        """Player ids, names, numbers and roles for a team."""
        return json.dumps(_tools(ctx).roster(team))

    return server
