"""Replays a match through the stats engine and the agent workflow.

Yields everything a renderer needs, in match order: raw events, stat
snapshots, overlays and agent traces. The API paces it in real time (or at
a speed-up); the CLI and evaluations run it flat out.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterable

from pitchside import overlays
from pitchside.agents.pipeline import Batch, Job, build_agents, build_workflow
from pitchside.stats.state import MatchState
from pitchside.tools import StatsTools

BATCH_EVERY_MS = 20_000  # the Director sees new candidates every 20 s of match time
URGENT = {"goal", "card", "big_chance"}
BROADCAST_DELAY_MS = 4_000


class Broadcast:
    def __init__(
        self,
        events: Iterable[dict],
        client=None,
        profiles: list[str] | None = None,
        langs: list[str] | None = None,
        state: MatchState | None = None,
    ) -> None:
        self.events = list(events)
        self.state = state or MatchState()
        self.tools = StatsTools(self.state)
        self.agents = build_agents(client, self.tools.agent_tools())
        self.workflow = build_workflow(self.agents)
        self.profiles = profiles or ["casual"]
        self.langs = langs or ["en"]
        self.aired: list[dict] = []
        self.recent_lines: list[str] = []
        self.pending: list[Job] = []
        self.last_batch_ms = 0

    @property
    def clubs(self) -> dict[str, str]:
        meta = self.state.meta
        return {meta[s]["code"]: meta[s]["name"] for s in ("home", "away")}

    async def run(self, speed: float | None = None) -> AsyncIterator[dict]:
        """speed=None runs as fast as possible; speed=10 plays ten times faster than real time."""
        wall0, match0 = time.perf_counter(), None
        for ev in self.events:
            if speed and ev["type"] != "match_start":
                match0 = ev["t_ms"] if match0 is None else match0
                due = (ev["t_ms"] - match0) / 1000 / speed
                wait = due - (time.perf_counter() - wall0)
                if wait > 0:
                    await asyncio.sleep(wait)

            moments = self.state.ingest(ev)
            yield {"kind": "event", "event": ev}
            if ev["type"] == "sprint":
                yield {
                    "kind": "overlay",
                    "overlay": overlays.player_tag(
                        ev["match_id"], ev, self.state.name(ev["player"])
                    ),
                }
            if (
                ev["type"] in {"goal", "physical", "period_end", "match_end"}
                or ev["event_id"] % 25 == 0
            ):
                yield {"kind": "snapshot", "snapshot": self.state.snapshot()}

            for m in moments:
                players = [p for p in {m.player, *(e.player for e in m.evidence)} if p]
                self.pending.append(
                    Job(
                        moment=m,
                        sheet=self.tools.fact_sheet(players),
                        names=self.state.names,
                        clubs=self.clubs,
                        profiles=self.profiles,
                        langs=self.langs,
                        recent_lines=list(self.recent_lines),
                    )
                )
            urgent = any(j.moment.type in URGENT for j in self.pending)
            if self.pending and (
                urgent
                or ev["t_ms"] - self.last_batch_ms >= BATCH_EVERY_MS
                or ev["type"] == "match_end"
            ):
                async for item in self.flush(ev["t_ms"], ev["match_id"]):
                    yield item

    async def flush(self, now_ms: int, match_id: str) -> AsyncIterator[dict]:
        batch, self.pending, self.last_batch_ms = Batch(self.pending, self.aired), [], now_ms
        result = await self.workflow.run(batch)
        for job in result.get_outputs():
            m = job.moment
            self.aired.append({"type": m.type, "minute": m.minute, "moment_id": m.id})
            self.recent_lines.append(job.caption["line"])
            agents = [step["agent"] for step in job.trace]
            for lang, by_profile in job.translations.items():
                for profile, cap in by_profile.items():
                    yield {
                        "kind": "overlay",
                        "minute": m.minute,
                        "overlay": overlays.insight_card(
                            m,
                            match_id,
                            cap["headline"],
                            cap["line"],
                            lang,
                            f"{profile}:{lang}",
                            start_t_ms=max(now_ms, m.t_ms + BROADCAST_DELAY_MS),
                            agents=agents,
                            verified=True,
                            fallback=job.fallback,
                        ),
                    }
            yield {
                "kind": "trace",
                "trace": {
                    "moment_id": m.id,
                    "minute": m.minute,
                    "type": m.type,
                    "steps": job.trace,
                },
            }
