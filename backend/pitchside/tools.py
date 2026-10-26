"""Stats tools: the only way agents get numbers.

One set of functions, published two ways:
- as an MCP server (mounted on the API at /mcp), which is what the deployed
  agents use and what any MCP client, such as GitHub Copilot in VS Code, can
  connect to;
- as in-process Agent Framework tools, for offline runs and evaluations.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from agent_framework import FunctionTool, tool
from mcp.server import MCPServer

from pitchside.stats.state import MatchState

WINDOWS = (60, 90, 180, 300, 600)


class StatsTools:
    def __init__(self, state: MatchState) -> None:
        self.state = state

    def match_snapshot(self) -> dict:
        """Score, minute, possession, momentum (-100 away on top .. +100 home on top), 5-minute chaos index and xG."""
        return self.state.snapshot()

    def team_metrics(self, team: str, window_s: int | None = None) -> dict:
        """Possession, passing, pass accuracy under pressure, pass difficulty, shots, xG, regains, PPDA and tempo
        for one team (3-letter code). window_s limits to the last N seconds of play; omit for the whole match."""
        return self.state.team_metrics(team.upper(), window_s)

    def player_summary(self, player_id: str) -> dict:
        """Passes, pass accuracy, shots, xG, goals, assists, regains, distance covered and top speed for a player id like KSC-09."""
        return self.state.player_summary(player_id.upper())

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

    def functions(self) -> list[Callable]:
        return [
            self.match_snapshot,
            self.team_metrics,
            self.player_summary,
            self.chaos_index,
            self.recent_moments,
            self.roster,
        ]

    def agent_tools(self) -> list[FunctionTool]:
        return [tool(f) for f in self.functions()]

    def fact_sheet(self, players: list[str]) -> dict:
        """Everything the Verifier will accept as true right now."""
        teams = self.state.teams
        return {
            "snapshot": self.match_snapshot(),
            "metrics": {t: {w: self.team_metrics(t, w) for w in (*WINDOWS, None)} for t in teams},
            "chaos": {w: self.state.chaos(w) for w in WINDOWS},
            "players": {p: self.player_summary(p) for p in players},
        }


def build_mcp_server(get_state: Callable[[], MatchState]) -> MCPServer:
    """MCP server over the live match. get_state returns the current MatchState."""
    server = MCPServer(
        name="pitchside-stats",
        instructions="Live statistics for the current synthetic match. Every number Pitchside shows comes from here.",
    )

    def _tools() -> StatsTools:
        return StatsTools(get_state())

    @server.tool()
    def match_snapshot() -> str:
        """Score, minute, possession, momentum, chaos index and xG for the live match."""
        return json.dumps(_tools().match_snapshot())

    @server.tool()
    def team_metrics(team: str, window_s: int | None = None) -> str:
        """Team metrics (possession, passing, pressure, xG, regains, PPDA, tempo). window_s = last N seconds."""
        return json.dumps(_tools().team_metrics(team, window_s))

    @server.tool()
    def player_summary(player_id: str) -> str:
        """Player stats for an id like KSC-09."""
        return json.dumps(_tools().player_summary(player_id))

    @server.tool()
    def chaos_index(window_s: int = 300) -> str:
        """Control (0) vs chaos (1) over the last window_s seconds."""
        return json.dumps(_tools().chaos_index(window_s))

    @server.tool()
    def recent_moments(limit: int = 5) -> str:
        """Most recent flagged moments with their evidence."""
        return json.dumps(_tools().recent_moments(limit))

    @server.tool()
    def roster(team: str) -> str:
        """Player ids, names, numbers and roles for a team."""
        return json.dumps(_tools().roster(team))

    return server
