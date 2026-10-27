"""Replays a match through the stats engine and the agent workflow.

Yields everything a renderer needs, in match order: raw events, stat
snapshots, overlays and agent traces. The API paces it in real time (or at
a speed-up); the CLI and evaluations run it flat out.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterable

from pitchside import overlays, translator
from pitchside.agents.pipeline import (
    Batch,
    EnglishReady,
    Job,
    build_agents,
    build_workflow,
    headline_for,
)
from pitchside.agents.templates import template_line
from pitchside.sim.league import Fixture, LeagueState
from pitchside.stats.metrics import pass_difficulty
from pitchside.stats.state import Evidence, MatchState, Moment
from pitchside.tools import StatsTools

WORKERS = 3  # moments handled in parallel during live play
BATCH_EVERY_MS = 10_000  # the Director sees new candidates every 10 s of match time
URGENT = {"goal", "card", "big_chance", "great_save", "half_time_recap", "full_time_recap"}
FAST = {"goal", "card", "big_chance", "great_save"}  # shown instantly from templates
BROADCAST_DELAY_MS = 4_000
MAX_GAP_MS = 6_000  # longest pause between two events in live playback


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
        league: LeagueState | None = None,
    ) -> None:
        self.events = list(events)
        self.state = state or MatchState()
        # The rest of the matchday: other fixtures play alongside and move the live table.
        self.league = league
        self.state.league = league
        self.featured = next(iter(league.fixtures)) if league else None
        self.others: list[Fixture] = list(league.fixtures.values())[1:] if league else []
        self.cursor = {f.id: 0 for f in self.others}
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
        if self.league:
            return dict(self.league.names)
        meta = self.state.meta
        return {meta[s]["code"]: meta[s]["name"] for s in ("home", "away")}

    def _flash(self, m: Moment, match_id: str) -> dict:
        """Fast path: a verified template caption on screen at once; the agents' caption replaces it."""
        card = overlays.insight_card(
            m,
            match_id,
            headline_for(m, self.clubs, self.state.names),
            template_line(m, self.state.names, self.clubs),
            "en",
            "flash:en",
            start_t_ms=m.t_ms,
            agents=["template"],
            verified=True,
            fallback=True,
        )
        card["provenance"]["fast"] = True
        return card

    async def _flash_in(self, flash: dict, lang: str, out: asyncio.Queue) -> None:
        texts = await translator.translate(
            [flash["content"]["headline"], flash["content"]["body"]], lang
        )
        if not texts:
            return
        card = {
            **flash,
            "overlay_id": f"{flash['overlay_id']}-{lang}",
            "profile_key": f"flash:{lang}",
            "content": {**flash["content"], "headline": texts[0], "body": texts[1], "lang": lang},
        }
        out.put_nowait(
            {"kind": "overlay", "minute": flash["anchor_t_ms"] // 60000 + 1, "overlay": card}
        )

    def _job(self, m: Moment) -> Job:
        return Job(
            moment=m,
            sheet={},
            names=self.state.names,
            clubs=self.clubs,
            profiles=self.profiles,
            langs=self.langs,
            players=[p for p in {m.player, *(e.player for e in m.evidence), *self.followed} if p],
        )

    def _league_moment(self, f: Fixture, ev: dict, before: dict[str, int]) -> Moment:
        """A goal elsewhere, with what it does to the live table."""
        lg = self.league
        after = {r["code"]: r["pos"] for r in lg.table()}
        score = f"{f.home} {f.score[f.home]}-{f.score[f.away]} {f.away}"
        evidence = [
            Evidence("score_elsewhere", score),
            Evidence("other_match_minute", ev.get("minute", 0)),
            Evidence("live_position", after[ev["team"]], ev["team"]),
        ]
        moved = []
        for code in (f.home, f.away, *self.state.teams):
            if after[code] != before[code] and code not in moved:
                moved.append(code)
                evidence += [
                    Evidence("live_position", after[code], code),
                    Evidence("position_before", before[code], code),
                ]
        featured_moved = any(c in self.state.teams for c in moved)
        return Moment(
            id=f"lg-{f.id}-{ev['event_id']}",
            type="around_the_league",
            t_ms=self.state.t_ms,
            minute=self.state.minute,
            team=ev["team"],
            player=None,
            significance=62 if featured_moved else 50,
            summary=f"Elsewhere: {lg.names[f.home]} {f.score[f.home]}-{f.score[f.away]} {lg.names[f.away]}",
            evidence=evidence,
        )

    def _recap_moment(self, ev: dict) -> Moment:
        """Half-time or full-time: the facts a recap may use, gathered from the stats engine."""
        st = self.state
        kind = "half_time_recap" if ev["period"] == 1 else "full_time_recap"
        a, b = st.teams
        ev_list = [Evidence("score", st.score_line())]
        for t in (a, b):
            m = st.team_metrics(t)
            ev_list += [
                Evidence("possession_pct", m["possession_pct"], t),
                Evidence("xg", m["xg"], t),
                Evidence("shots", m["shots"], t),
            ]
        for e in st.events:
            if e["type"] == "goal":
                ev_list.append(Evidence("goal_minute", e["minute"], e["team"], e["player"]))
        players = [p for p in st.names if st.player[p]["passes"]]
        if players:
            top = max(players, key=lambda p: st.player[p]["passes"])
            ev_list.append(Evidence("passes", st.player[top]["passes"], st.team_of(top), top))
        ran = [p for p in st.physical if st.physical[p].get("distance_m")]
        if ran:
            far = max(ran, key=lambda p: st.physical[p]["distance_m"])
            km = round(st.physical[far]["distance_m"] / 1000, 1)
            ev_list.append(Evidence("distance_km", km, st.team_of(far), far))
        if self.league:
            for t in (a, b):
                ev_list.append(Evidence("live_position", self.league.position(t), t))
        label = "Half-time" if kind == "half_time_recap" else "Full-time"
        return Moment(
            id=f"recap-{ev['period']}",
            type=kind,
            t_ms=ev["t_ms"],
            minute=45 if ev["period"] == 1 else 90,
            team=None,
            player=None,
            significance=100,
            summary=f"{label}: {st.score_line()}",
            evidence=ev_list,
        )

    def _advance_league(self, t_ms: int) -> tuple[list[Moment], bool]:
        """Play the other fixtures up to t_ms. Returns new moments and whether any score changed."""
        moments, changed = [], False
        for f in self.others:
            i = self.cursor[f.id]
            while i < len(f.events) and f.events[i]["t_ms"] <= t_ms:
                e = f.events[i]
                before = {r["code"]: r["pos"] for r in self.league.table()}
                if self.league.apply(f.id, e):
                    changed = True
                    moments.append(self._league_moment(f, e, before))
                i += 1
            self.cursor[f.id] = i
        return moments, changed

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
        wall0, prev_t, played_ms = time.perf_counter(), None, 0.0
        for ev in self.events:
            if speed and ev["type"] != "match_start":
                # Like a broadcast cutting through a stoppage, long dead-ball gaps (goal
                # celebrations, goal kicks, throw-ins) are shortened in playback. The match
                # clock and every number keep the real time.
                if prev_t is not None:
                    played_ms += min(ev["t_ms"] - prev_t, MAX_GAP_MS)
                prev_t = ev["t_ms"]
                due = played_ms / 1000 / speed
                wait = due - (time.perf_counter() - wall0)
                if wait > 0:
                    await asyncio.sleep(wait)

            moments = self.state.ingest(ev)
            league_changed = False
            if self.league and ev["type"] != "match_start":
                # When our match ends, let the other fixtures finish their stoppage time too.
                until = 10**9 if ev["type"] == "match_end" else ev["t_ms"]
                elsewhere, league_changed = self._advance_league(until)
                league_changed |= self.league.apply(self.featured, ev)
                moments = [*moments, *elsewhere]
            if ev["type"] == "period_end":
                moments = [*moments, self._recap_moment(ev)]
            if ev["type"] in ("pass", "clearance"):
                # Pass quality for the analyst strip: distance, difficulty rating, ball speed.
                yield {"kind": "event", "event": {**ev, "difficulty": pass_difficulty(ev)}}
            else:
                yield {"kind": "event", "event": ev}
            if self.league and (
                league_changed
                or ev["type"] in {"physical", "period_start", "period_end", "match_end"}
            ):
                yield {"kind": "league", "league": self.league.snapshot()}
            if ev["type"] == "sprint":
                name = self.state.name(ev["player"])
                yield {"kind": "overlay", "overlay": overlays.player_tag(ev["match_id"], ev, name)}
            if (
                ev["type"] in {"goal", "physical", "period_end", "match_end"}
                or ev["event_id"] % 25 == 0
            ):
                yield {"kind": "snapshot", "snapshot": self.state.snapshot()}
                for pid in self.followed:
                    yield {"kind": "player", "player": self.state.player_summary(pid)}

            for m in moments:
                self.pending.append(self._job(m))
                if m.type in FAST or (m.significance >= 60 and not m.type.endswith("_recap")):
                    flash = self._flash(m, ev["match_id"])
                    yield {"kind": "overlay", "minute": m.minute, "overlay": flash}
                    # Viewers in other languages get it instantly too, through Azure Translator.
                    if workers and translator.enabled():
                        for lang in (x for x in self.langs if x != "en"):
                            asyncio.create_task(self._flash_in(flash, lang, out))
            urgent = any(j.moment.type in URGENT for j in self.pending)
            due_now = ev["t_ms"] - self.last_batch_ms >= BATCH_EVERY_MS or ev["type"] == "match_end"
            if self.pending and (urgent or due_now):
                batch, self.pending, self.last_batch_ms = self.pending, [], ev["t_ms"]
                if workers:
                    batches.put_nowait((batch, ev["match_id"]))
                    yield {
                        "kind": "pending",
                        "moments": [
                            {"id": j.moment.id, "type": j.moment.type, "minute": j.moment.minute}
                            for j in batch
                        ],
                    }
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
        # A fresh workflow run per batch, so parallel workers never share run state. Streaming lets
        # English captions air as soon as Persona finishes, before the translations come back.
        sent_en: set[str] = set()
        stream = build_workflow(self.agents).run(Batch(jobs, self.aired), stream=True)
        async for event in stream:
            if event.type not in ("intermediate", "output"):
                continue
            if isinstance(event.data, EnglishReady):
                job = event.data.job
                sent_en.add(job.moment.id)
                self.aired.append(
                    {
                        "type": job.moment.type,
                        "minute": job.moment.minute,
                        "moment_id": job.moment.id,
                    }
                )
                self.recent_lines.append(job.caption["line"])
                for item in self._cards(job, match_id, {"en": job.variants}):
                    yield item
                continue
            job = event.data
            if job.moment.id not in sent_en:
                self.aired.append(
                    {
                        "type": job.moment.type,
                        "minute": job.moment.minute,
                        "moment_id": job.moment.id,
                    }
                )
                self.recent_lines.append(job.caption["line"])
            langs = {
                k: v
                for k, v in job.translations.items()
                if k != "en" or job.moment.id not in sent_en
            }
            for item in self._cards(job, match_id, langs):
                yield item
            m = job.moment
            trace = {"moment_id": m.id, "minute": m.minute, "type": m.type, "steps": job.trace}
            yield {"kind": "trace", "trace": trace}

    def _cards(self, job: Job, match_id: str, by_lang: dict[str, dict]) -> list[dict]:
        m = job.moment
        agents = [step["agent"] for step in job.trace]
        start = max(self.state.t_ms, m.t_ms + BROADCAST_DELAY_MS)
        insight = job.insight or {}
        why = {
            "claim": insight.get("claim", ""),
            "reason": insight.get("why", ""),
            "cited": job.cited,
        }
        out = []
        for lang, by_profile in by_lang.items():
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
                    why=why,
                )
                out.append({"kind": "overlay", "minute": m.minute, "overlay": card})
        return out
