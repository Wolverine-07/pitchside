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

WORKERS = 3  # moments handled in parallel during live play
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
        deep_client=None,
        analyst_tools: list | None = None,
    ) -> None:
        self.events = list(events)
        self.state = state or MatchState()
        self.tools = StatsTools(self.state)
        self.agents = build_agents(client, analyst_tools or self.tools.agent_tools(), deep_client)
        self.workflow = build_workflow(self.agents)
        self.profiles = profiles or ["casual"]
        self.followed = [p.split(":", 1)[1] for p in self.profiles if p.startswith("player:")]
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
        """speed=None runs as fast as possible and waits for the agents at every batch, so runs are
        repeatable. With a speed (10 = ten times real time) the match keeps streaming while a
        background worker runs the agents, and their overlays arrive as soon as they are ready."""
        out: asyncio.Queue = asyncio.Queue()
        batches: asyncio.Queue = asyncio.Queue()
        workers = (
            [asyncio.create_task(self._worker(batches, out)) for _ in range(WORKERS)]
            if speed
            else []
        )
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
                name = self.state.name(ev["player"])
                yield {"kind": "overlay", "overlay": overlays.player_tag(ev["match_id"], ev, name)}
            if (
                ev["type"] in {"goal", "physical", "period_end", "match_end"}
                or ev["event_id"] % 25 == 0
            ):
                yield {"kind": "snapshot", "snapshot": self.state.snapshot()}

            for m in moments:
                self.pending.append(
                    Job(
                        moment=m,
                        sheet={},
                        names=self.state.names,
                        clubs=self.clubs,
                        profiles=self.profiles,
                        langs=self.langs,
                        players=[
                            p
                            for p in {m.player, *(e.player for e in m.evidence), *self.followed}
                            if p
                        ],
                    )
                )
            urgent = any(j.moment.type in URGENT for j in self.pending)
            due_now = ev["t_ms"] - self.last_batch_ms >= BATCH_EVERY_MS or ev["type"] == "match_end"
            if self.pending and (urgent or due_now):
                batch, self.pending, self.last_batch_ms = self.pending, [], ev["t_ms"]
                if workers:
                    batches.put_nowait((batch, ev["match_id"]))
                else:
                    async for item in self.flush(batch, ev["match_id"]):
                        yield item
            while not out.empty():
                yield out.get_nowait()

        if workers:
            for _ in workers:
                batches.put_nowait(None)
            while not all(w.done() for w in workers) or not out.empty():
                try:
                    yield await asyncio.wait_for(out.get(), 0.25)
                except TimeoutError:
                    continue
            for w in workers:
                w.result()

    async def _worker(self, batches: asyncio.Queue, out: asyncio.Queue) -> None:
        while (item := await batches.get()) is not None:
            batch, match_id = item
            async for result in self.flush(batch, match_id):
                out.put_nowait(result)

    async def flush(self, jobs: list[Job], match_id: str) -> AsyncIterator[dict]:
        # Facts are taken when the agents start, so they match what the Analyst's tools return.
        for job in jobs:
            job.sheet = self.tools.fact_sheet(job.players)
            job.recent_lines = list(self.recent_lines)
        # A fresh workflow run per batch, so parallel workers never share run state.
        result = await build_workflow(self.agents).run(Batch(jobs, self.aired))
        for job in result.get_outputs():
            m = job.moment
            self.aired.append({"type": m.type, "minute": m.minute, "moment_id": m.id})
            self.recent_lines.append(job.caption["line"])
            agents = [step["agent"] for step in job.trace]
            start = max(self.state.t_ms, m.t_ms + BROADCAST_DELAY_MS)
            for lang, by_profile in job.translations.items():
                for profile, cap in by_profile.items():
                    card = overlays.insight_card(
                        m,
                        match_id,
                        cap["headline"],
                        cap["line"],
                        lang,
                        f"{profile}:{lang}",
                        start_t_ms=start,
                        agents=agents,
                        verified=True,
                        fallback=job.fallback,
                    )
                    yield {"kind": "overlay", "minute": m.minute, "overlay": card}
            trace = {"moment_id": m.id, "minute": m.minute, "type": m.type, "steps": job.trace}
            yield {"kind": "trace", "trace": trace}
