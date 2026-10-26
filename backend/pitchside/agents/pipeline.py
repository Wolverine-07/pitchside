"""The agent workflow, built with Microsoft Agent Framework.

    Director ─▶ Analyst ─▶ Narrator ─▶ Verifier ─┬─ pass ──────────▶ Persona ─▶ Linguist ─▶ output
                              ▲                  ├─ retry (≤ 2) ─▶ Narrator
                              └──────────────────┘
                                                 └─ fail twice ──▶ Template ─▶ Persona

Shared state is the live MatchState. Agents read numbers through the stats
tools; only the Verifier decides what is true, and it does so in plain code.
Every executor falls back to a deterministic path when its model call fails,
times out, or the run is templates-only, so the broadcast never waits.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Never

from agent_framework import (
    Agent,
    Case,
    Default,
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)

from pitchside.stats.state import Moment

from . import prompts
from .templates import template_line
from .verify import check_citations, check_names, check_numbers, verify

MAX_ATTEMPTS = 2
CALL_TIMEOUT_S = 12.0
ALWAYS_AIR = {"goal", "big_chance", "card"}


@dataclass
class Job:
    moment: Moment
    sheet: dict  # StatsTools.fact_sheet() at the time of the moment
    names: dict[str, str]
    clubs: dict[str, str]
    profiles: list[str]
    langs: list[str]
    players: list[str] = field(default_factory=list)
    recent_lines: list[str] = field(default_factory=list)
    insight: dict | None = None
    cited: list[dict] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    caption: dict | None = None
    attempt: int = 0
    problems: list[str] = field(default_factory=list)
    status: str = "new"
    fallback: bool = False
    variants: dict[str, dict] = field(default_factory=dict)
    translations: dict[str, dict[str, dict]] = field(default_factory=dict)
    trace: list[dict] = field(default_factory=list)

    def facts(self) -> dict:
        """What a caption may state: the moment, the Analyst's verified citations, minute and score."""
        return {
            "moment": {
                "minute": self.moment.minute,
                "evidence": [e.__dict__ for e in self.moment.evidence],
                "players": [self.moment.player] if self.moment.player else [],
            },
            "cited": self.cited,
            "score": self.sheet["snapshot"]["score"],
        }

    def log(self, agent: str, started: float, status: str, note: str = "") -> None:
        self.trace.append(
            {
                "agent": agent,
                "ms": round((time.perf_counter() - started) * 1000),
                "status": status,
                "note": note,
            }
        )


@dataclass
class Batch:
    jobs: list[Job]
    aired: list[dict]  # recent airtime log: {"type", "minute", "moment_id"}


def parse_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1])


async def ask(agent: Agent | None, prompt: str) -> dict | None:
    """One model call with a time budget. None means: use the deterministic path."""
    if agent is None:
        return None
    try:
        response = await asyncio.wait_for(agent.run(prompt), CALL_TIMEOUT_S)
        return parse_json(response.text)
    except Exception:  # noqa: BLE001 - timeout, rate limit, content filter, bad JSON all degrade the same way
        return None


def describe(m: Moment, names: dict[str, str]) -> dict:
    d = m.to_dict()
    d["player_name"] = names.get(m.player or "")
    return d


class DirectorExec(Executor):
    def __init__(self, agent: Agent | None) -> None:
        super().__init__(id="director")
        self.agent = agent

    @handler
    async def choose(self, batch: Batch, ctx: WorkflowContext[Job]) -> None:
        t0 = time.perf_counter()
        by_id = {j.moment.id: j for j in batch.jobs}
        must = [j for j in batch.jobs if j.moment.type in ALWAYS_AIR]
        picked: list[Job] = []
        reply = None
        if len(batch.jobs) > len(must):
            reply = await ask(
                self.agent,
                json.dumps(
                    {
                        "candidates": [describe(j.moment, j.names) for j in batch.jobs],
                        "recently_aired": batch.aired[-6:],
                    }
                ),
            )
        if reply and isinstance(reply.get("air"), list):
            picked = [by_id[i] for i in reply["air"] if i in by_id][:2]
            note, status = reply.get("reason", ""), "ok"
        else:
            recent_types = {a["type"] for a in batch.aired[-3:]}
            ranked = sorted(batch.jobs, key=lambda j: -j.moment.significance)
            picked = [
                j
                for j in ranked
                if j.moment.significance >= 45 and j.moment.type not in recent_types
            ][:1]
            note, status = (
                "rule: highest significance, varied type",
                "fallback" if self.agent else "rule",
            )
            if reply is None and len(batch.jobs) == len(must):
                note, status = "always airs", "rule"
        for j in must:
            if j not in picked:
                picked.insert(0, j)
        for j in picked:
            j.log("director", t0, status, note)
            await ctx.send_message(j)


class AnalystExec(Executor):
    def __init__(self, agent: Agent | None) -> None:
        super().__init__(id="analyst")
        self.agent = agent

    @handler
    async def analyse(self, job: Job, ctx: WorkflowContext[Job]) -> None:
        t0 = time.perf_counter()
        reply = await ask(
            self.agent, json.dumps({"moment": describe(job.moment, job.names), "clubs": job.clubs})
        )
        if reply and reply.get("claim"):
            kept, problems = check_citations(
                reply.get("numbers", []), job.sheet, [e.__dict__ for e in job.moment.evidence]
            )
            job.insight, job.cited = reply, kept
            note = f"{len(kept)} numbers confirmed" + (
                f", {len(problems)} dropped" if problems else ""
            )
            job.log("analyst", t0, "ok" if not problems else "corrected", note)
        else:
            job.insight = {"claim": job.moment.summary, "why": "", "numbers": []}
            job.log("analyst", t0, "fallback" if self.agent else "rule", "moment summary used")
        await ctx.send_message(job)


class NarratorExec(Executor):
    def __init__(self, agent: Agent | None) -> None:
        super().__init__(id="narrator")
        self.agent = agent

    @handler
    async def narrate(self, job: Job, ctx: WorkflowContext[Job]) -> None:
        t0 = time.perf_counter()
        prompt = {
            "insight": {k: job.insight.get(k) for k in ("claim", "why")} if job.insight else {},
            "numbers_you_may_use": job.cited + [e.__dict__ for e in job.moment.evidence],
            "match_minute_now": f"{job.moment.minute} of 90",
            "score": job.sheet["snapshot"]["score"],
            "clubs": job.clubs,
            "player": job.names.get(job.moment.player or ""),
            "recent_lines": job.recent_lines[-5:],
        }
        if job.problems:
            prompt["verifier_rejected_previous_draft_because"] = job.problems
        reply = await ask(self.agent, json.dumps(prompt))
        job.candidates = (reply or {}).get("candidates", [])[:2]
        status = "ok" if job.candidates else ("fallback" if self.agent else "rule")
        job.log(
            "narrator", t0, status, f"draft {job.attempt + 1}" if job.candidates else "no draft"
        )
        await ctx.send_message(job)


class VerifierExec(Executor):
    def __init__(self, can_retry: bool) -> None:
        super().__init__(id="verifier")
        self.can_retry = can_retry

    @handler
    async def check(self, job: Job, ctx: WorkflowContext[Job]) -> None:
        t0 = time.perf_counter()
        facts = job.facts()
        problems: list[str] = []
        for cand in job.candidates:
            text = f"{cand.get('headline', '')}. {cand.get('line', '')}"
            result = verify(text, facts, job.names)
            if result:
                h = cand.get("headline", "").strip()
                cand["headline"] = h[:1].upper() + h[1:]
                job.caption, job.status = cand, "pass"
                job.log("verifier", t0, "pass", f"draft {job.attempt + 1} accepted")
                await ctx.send_message(job)
                return
            problems += result.problems
        job.attempt += 1
        job.problems = sorted(set(problems)) or ["no usable draft"]
        job.status = (
            "retry"
            if self.can_retry and job.candidates and job.attempt < MAX_ATTEMPTS
            else "fallback"
        )
        job.log("verifier", t0, "reject", "; ".join(job.problems[:3]))
        await ctx.send_message(job)


class TemplateExec(Executor):
    def __init__(self) -> None:
        super().__init__(id="template")

    @handler
    async def fill(self, job: Job, ctx: WorkflowContext[Job]) -> None:
        t0 = time.perf_counter()
        line = template_line(job.moment, job.names, job.clubs)
        job.caption = {"headline": headline_for(job.moment, job.clubs), "line": line}
        job.fallback = True
        job.log("template", t0, "ok", "verified template line")
        await ctx.send_message(job)


class PersonaExec(Executor):
    def __init__(self, agent: Agent | None) -> None:
        super().__init__(id="persona")
        self.agent = agent

    @handler
    async def personalise(self, job: Job, ctx: WorkflowContext[Job]) -> None:
        t0 = time.perf_counter()
        base = job.caption
        wanted = [p for p in job.profiles if p != "casual"] if job.fallback else job.profiles
        reply = (
            await ask(
                self.agent,
                json.dumps(
                    {
                        "caption": base,
                        "profiles": wanted,
                        "facts": job.cited + [e.__dict__ for e in job.moment.evidence],
                        "clubs": job.clubs,
                        "player_names": {
                            p.split(":")[1]: job.names.get(p.split(":")[1])
                            for p in wanted
                            if p.startswith("player:")
                        },
                    }
                ),
            )
            if wanted
            else None
        )
        variants = (reply or {}).get("variants", {})
        kept = 0
        facts = job.facts()
        for profile in job.profiles:
            v = variants.get(profile)
            if v and verify(
                f"{v.get('headline', '')}. {v.get('line', '')}", facts, job.names, live=False
            ):
                job.variants[profile] = v
                kept += 1
            else:
                job.variants[profile] = base
        status = "ok" if reply else ("fallback" if self.agent else "rule")
        job.log("persona", t0, status, f"{kept}/{len(job.profiles)} profiles rewritten")
        await ctx.send_message(job)


class LinguistExec(Executor):
    def __init__(self, agent: Agent | None) -> None:
        super().__init__(id="linguist")
        self.agent = agent

    @handler
    async def translate(self, job: Job, ctx: WorkflowContext[Never, Job]) -> None:
        t0 = time.perf_counter()
        job.translations = {"en": dict(job.variants)}
        others = [lang for lang in job.langs if lang != "en"]
        reply = (
            await ask(
                self.agent,
                json.dumps(
                    {
                        "languages": {lang: prompts.LANGUAGES[lang] for lang in others},
                        "captions": job.variants,
                    }
                ),
            )
            if others
            else None
        )
        out = (reply or {}).get("translations", {})
        facts = job.facts()
        kept = 0
        for lang in others:
            job.translations[lang] = {}
            for profile, caption in job.variants.items():
                t = out.get(lang, {}).get(profile)
                text = f"{(t or {}).get('headline', '')}. {(t or {}).get('line', '')}"
                if t and not check_numbers(text, facts) and not check_names(text, facts, job.names):
                    job.translations[lang][profile] = t
                    kept += 1
                else:
                    job.translations[lang][profile] = (
                        caption  # English rather than an unchecked line
                    )
        total = len(others) * len(job.variants)
        status = "ok" if reply or not others else ("fallback" if self.agent else "rule")
        job.log(
            "linguist",
            t0,
            status,
            f"{kept}/{total} translations kept" if others else "English only",
        )
        await ctx.yield_output(job)


def headline_for(m: Moment, clubs: dict[str, str]) -> str:
    team = clubs.get(m.team or "", "")
    return {
        "goal": f"Goal, {team}",
        "big_chance": "Big chance",
        "pressing_spell": f"{team} turn up the press",
        "momentum_swing": f"Momentum with {team}",
        "chaos_spike": "Chaos takes over",
        "card": "Card shown",
        "player_speed": "Top speed",
        "milestone": "Milestone",
    }.get(m.type, m.type.replace("_", " ").title())


def build_agents(client: Any, tools: list, deep_client: Any = None) -> dict[str, Agent | None]:
    if client is None:
        return dict.fromkeys(("director", "analyst", "narrator", "persona", "linguist"))
    return {
        "director": Agent(client, prompts.DIRECTOR, name="Director"),
        "analyst": Agent(deep_client or client, prompts.ANALYST, name="Analyst", tools=tools),
        "narrator": Agent(client, prompts.NARRATOR, name="Narrator"),
        "persona": Agent(client, prompts.PERSONA, name="Persona"),
        "linguist": Agent(client, prompts.LINGUIST, name="Linguist"),
    }


def build_workflow(agents: dict[str, Agent | None]):
    director = DirectorExec(agents["director"])
    analyst = AnalystExec(agents["analyst"])
    narrator = NarratorExec(agents["narrator"])
    verifier = VerifierExec(can_retry=agents["narrator"] is not None)
    template = TemplateExec()
    persona = PersonaExec(agents["persona"])
    linguist = LinguistExec(agents["linguist"])
    return (
        WorkflowBuilder(name="pitchside", start_executor=director, max_iterations=200)
        .add_edge(director, analyst)
        .add_edge(analyst, narrator)
        .add_edge(narrator, verifier)
        .add_switch_case_edge_group(
            verifier,
            [
                Case(lambda j: j.status == "retry", narrator),
                Case(lambda j: j.status == "fallback", template),
                Default(persona),
            ],
        )
        .add_edge(template, persona)
        .add_edge(persona, linguist)
        .build()
    )
