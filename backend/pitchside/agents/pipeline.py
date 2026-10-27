"""The agent workflow, built with Microsoft Agent Framework.

    Director ─▶ Analyst ─▶ Narrator ─▶ Verifier ─▶ Critic ─┬─ pass ──────────▶ Persona ─▶ Linguist ─▶ output
                              ▲                            ├─ retry (≤ 2) ─▶ Narrator
                              └────────────────────────────┘
                                                           └─ fail twice ──▶ Template ─▶ Persona
    (a Verifier reject skips the Critic and goes straight to retry or Template)

Shared state is the live MatchState. Agents read numbers through the stats
tools; only the Verifier (numbers, names, time) and the Critic (the reasons a
caption gives) decide what is true, and both do so in plain code.
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

from pitchside import translator
from pitchside.stats.state import Moment

from . import prompts
from .critic import check_reasons
from .templates import template_line
from .verify import check_audience, check_citations, check_names, check_numbers, verify

MAX_ATTEMPTS = 2
CALL_TIMEOUT_S = 12.0
ALWAYS_AIR = {
    "goal",
    "big_chance",
    "card",
    "half_time_recap",
    "full_time_recap",
    "match_preview",
    "match_pulse",
}


def tracked(metric: str, sheet: dict) -> dict:
    """The live values of one metric for both clubs, for a viewer who follows that number."""
    snap = sheet.get("snapshot") or {}
    teams = snap.get("teams") or {}
    metrics = sheet.get("metrics") or {}
    values = {
        "possession": lambda: snap.get("possession_pct"),
        "chances": lambda: snap.get("xg"),
        "shots": lambda: {t: v["shots"] for t, v in teams.items()},
        "pressing": lambda: {
            t: (m.get(None) or {}).get("high_regains") for t, m in metrics.items()
        },
        "win": lambda: snap.get("win_probability_pct"),
    }
    get = values.get(metric)
    return {metric: get()} if get else {}


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
    passed: list[dict] = field(default_factory=list)  # drafts the Verifier accepted, for the Critic
    unsupported: list[str] = field(
        default_factory=list
    )  # the Analyst's reasons the Critic rejected
    caption: dict | None = None
    attempt: int = 0
    problems: list[str] = field(default_factory=list)
    status: str = "new"
    fallback: bool = False
    variants: dict[str, dict] = field(default_factory=dict)
    translations: dict[str, dict[str, dict]] = field(default_factory=dict)
    trace: list[dict] = field(default_factory=list)

    def facts(self, profile: str | None = None) -> dict:
        """What a caption may state: the moment, the Analyst's verified citations, minute and score.

        In player-focus mode the followed player may be named, with his own stats."""
        followed = profile.split(":", 1)[1] if profile and profile.startswith("player:") else None
        extra = (
            {"followed": {followed: self.sheet.get("players", {}).get(followed)}}
            if followed
            else {}
        )
        if profile and profile.startswith("metric:"):
            extra["tracked"] = tracked(profile.split(":", 1)[1], self.sheet)
        return {
            **extra,
            "moment": {
                "minute": self.moment.minute,
                "evidence": [e.__dict__ for e in self.moment.evidence],
                "players": [self.moment.player] if self.moment.player else [],
            },
            "cited": self.cited,
            "score": self.sheet["snapshot"]["score"],
        }

    def reasons(self, text: str) -> list[str]:
        """The Critic's verdict on the reasons a line gives."""
        return check_reasons(
            text,
            self.sheet,
            self.clubs,
            self.moment.type,
            self.moment.team,
            self.moment.minute,
        )

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
class EnglishReady:
    """Intermediate output: the English captions are verified and can air before translations finish."""

    job: Job


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
        if len(batch.jobs) - len(must) > 1:
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
            elif len(batch.jobs) - len(must) <= 1:
                note, status = "one candidate: rule decides, no model call", "rule"
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
        # The numbers analysts reach for most, handed over up front: most moments then need no tool
        # round trips at all, which is where the Analyst's time went. Tools stay available for more.
        sheet = job.sheet
        primed = {
            "snapshot": sheet.get("snapshot"),
            "last_5_minutes": {t: sheet["metrics"][t][300] for t in sheet.get("metrics", {})},
            "players": sheet.get("players"),
            "league": sheet.get("league"),
        }
        reply = await ask(
            self.agent,
            json.dumps(
                {"moment": describe(job.moment, job.names), "clubs": job.clubs, "context": primed},
                default=str,
            ),
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
            t1 = time.perf_counter()
            job.unsupported = job.reasons(f"{reply.get('claim', '')} {reply.get('why', '')}")
            if job.unsupported:
                job.log("critic", t1, "corrected", "; ".join(job.unsupported[:2]))
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
        if job.moment.type.endswith("_recap"):
            prompt["format"] = (
                "RECAP: headline of at most eight words, then three short sentences (at most 60 words) "
                "telling the story of the half: the result, why it went that way, and one standout. "
                "You may use up to four numbers."
            )
        if job.unsupported:
            prompt["critic_says_these_reasons_are_not_true"] = job.unsupported
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
        job.passed = []
        for cand in job.candidates:
            text = f"{cand.get('headline', '')}. {cand.get('line', '')}"
            recap = job.moment.type.endswith("_recap")
            result = verify(text, facts, job.names, live=not recap)
            if result and (audience := check_audience(text, "casual", 4 if recap else 2)):
                # The base caption is what casual viewers see if a rewrite fails, so it must suit them.
                result.ok, result.problems = False, audience
            if result:
                h = cand.get("headline", "").strip()
                cand["headline"] = h[:1].upper() + h[1:]
                job.passed.append(cand)
            else:
                problems += result.problems
        if job.passed:
            job.status = "pass"
            job.log("verifier", t0, "pass", f"draft {job.attempt + 1} accepted")
            await ctx.send_message(job)
            return
        job.attempt += 1
        job.problems = sorted(set(problems)) or ["no usable draft"]
        job.status = (
            "retry"
            if self.can_retry and job.candidates and job.attempt < MAX_ATTEMPTS
            else "fallback"
        )
        job.log("verifier", t0, "reject", "; ".join(job.problems[:3]))
        await ctx.send_message(job)


class CriticExec(Executor):
    """Checks the reasons a verified draft gives against the stats engine. Plain code."""

    def __init__(self, can_retry: bool) -> None:
        super().__init__(id="critic")
        self.can_retry = can_retry

    @handler
    async def check(self, job: Job, ctx: WorkflowContext[Job]) -> None:
        t0 = time.perf_counter()
        problems: list[str] = []
        for cand in job.passed:
            found = job.reasons(f"{cand.get('headline', '')}. {cand.get('line', '')}")
            if not found:
                job.caption, job.status = cand, "pass"
                job.log("critic", t0, "pass", "every reason backed by the stats engine")
                await ctx.send_message(job)
                return
            problems += found
        job.attempt += 1
        job.problems = sorted(set(problems))
        job.status = "retry" if self.can_retry and job.attempt < MAX_ATTEMPTS else "fallback"
        job.log("critic", t0, "reject", "; ".join(job.problems[:2]))
        await ctx.send_message(job)


class TemplateExec(Executor):
    def __init__(self) -> None:
        super().__init__(id="template")

    @handler
    async def fill(self, job: Job, ctx: WorkflowContext[Job]) -> None:
        t0 = time.perf_counter()
        line = template_line(job.moment, job.names, job.clubs)
        job.caption = {"headline": headline_for(job.moment, job.clubs, job.names), "line": line}
        job.fallback = True
        job.log("template", t0, "ok", "verified template line")
        await ctx.send_message(job)


class PersonaExec(Executor):
    """Rewrites the verified caption for each viewer. Rejected rewrites get one retry with the reasons."""

    def __init__(self, agent: Agent | None) -> None:
        super().__init__(id="persona")
        self.agent = agent

    @staticmethod
    def _problems(job: Job, profile: str, v: dict | None) -> list[str]:
        if not v or not v.get("line"):
            return ["no rewrite"]
        text = f"{v.get('headline', '')}. {v.get('line', '')}"
        check = verify(text, job.facts(profile), job.names, live=False)
        return (
            check.problems
            or check_audience(text, profile, 4 if job.moment.type.endswith("_recap") else 2)
            or job.reasons(text)
        )

    def _prompt(
        self, job: Job, profiles: list[str], fix: dict[str, list[str]] | None = None
    ) -> str:
        followed = [p.split(":", 1)[1] for p in profiles if p.startswith("player:")]
        body = {
            "caption": job.caption,
            "profiles": profiles,
            "facts": job.cited + [e.__dict__ for e in job.moment.evidence],
            "match_minute_now": f"{job.moment.minute} of 90",
            "clubs": job.clubs,
            "followed_players": {
                pid: {"name": job.names.get(pid), "stats": job.sheet.get("players", {}).get(pid)}
                for pid in followed
            },
        }
        metrics = [p.split(":", 1)[1] for p in profiles if p.startswith("metric:")]
        if metrics:
            body["tracked_metric_now"] = {m: tracked(m, job.sheet).get(m) for m in metrics}
        if fix:
            body["verifier_rejected_these_rewrites_because"] = fix
        return json.dumps(body)

    @handler
    async def personalise(self, job: Job, ctx: WorkflowContext[Job, EnglishReady]) -> None:
        t0 = time.perf_counter()
        wanted = [p for p in job.profiles if p != "casual"] if job.fallback else list(job.profiles)
        retried = 0

        async def one(profile: str) -> tuple[dict | None, list[str], bool]:
            """One viewer's rewrite, with one retry carrying the Verifier's reasons."""
            reply = await ask(self.agent, self._prompt(job, [profile]))
            v = ((reply or {}).get("variants") or {}).get(profile)
            problems = self._problems(job, profile, v)
            if problems and reply:
                again = await ask(self.agent, self._prompt(job, [profile], {profile: problems}))
                v2 = ((again or {}).get("variants") or {}).get(profile)
                if not self._problems(job, profile, v2):
                    return v2, [], True
            return v, problems, False

        # Every viewer's version is written at the same time: the step takes as long as the slowest one.
        results = await asyncio.gather(*(one(p) for p in wanted)) if wanted and self.agent else []
        variants = {p: r[0] for p, r in zip(wanted, results)}
        failed = {p: r[1] for p, r in zip(wanted, results) if r[1]}
        if not self.agent:
            failed = {p: ["no model"] for p in wanted}
        retried = sum(r[2] for r in results)
        reply = bool(results)

        for p in job.profiles:
            job.variants[p] = job.caption if p in failed or p not in wanted else variants[p]
        kept = len(wanted) - len(failed)
        note = f"{kept}/{len(job.profiles)} profiles rewritten"
        if retried:
            note += f" ({retried} fixed on retry)"
        if failed:
            note += "; kept base for " + "; ".join(
                f"{p}: {pr[0]}" for p, pr in list(failed.items())[:2]
            )
        status = "ok" if reply else ("fallback" if self.agent else "rule")
        job.log("persona", t0, status, note)
        await ctx.yield_output(EnglishReady(job))
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
        # One language per call, all in parallel: each viewer waits for their language only.
        results = await asyncio.gather(*(self._language(job, lang) for lang in others))
        notes, used_model = [], False
        for lang, (captions, how) in zip(others, results):
            job.translations[lang] = captions
            used_model |= how["model"] > 0
            parts = [f"{how['model']} agent"]
            if how["retry"]:
                parts.append(f"{how['retry']} fixed on retry")
            if how["translator"]:
                parts.append(f"{how['translator']} via Azure Translator")
            if how["english"]:
                parts.append(f"{how['english']} left in English")
            notes.append(f"{lang}: " + ", ".join(parts))
        status = "ok" if used_model or not others else ("fallback" if self.agent else "rule")
        job.log("linguist", t0, status, "; ".join(notes) if others else "English only")
        await ctx.yield_output(job)

    def _bad(self, job: Job, profile: str, t: dict | None) -> list[str]:
        if not t or not t.get("line"):
            return ["no translation"]
        text = f"{t.get('headline', '')}. {t.get('line', '')}"
        facts = job.facts(profile)
        return check_numbers(text, facts) + check_names(text, facts, job.names)

    async def _language(self, job: Job, lang: str) -> tuple[dict, dict]:
        """Agent translation, one retry with the reasons, then Azure Translator. English only as a last resort."""
        how = {"model": 0, "retry": 0, "translator": 0, "english": 0}
        name = prompts.LANGUAGES.get(lang, lang)
        reply = await ask(
            self.agent, json.dumps({"languages": {lang: name}, "captions": job.variants})
        )
        got = _by_lang(reply, lang, name)
        out, failed = {}, {}
        for profile in job.variants:
            problems = self._bad(job, profile, got.get(profile))
            if problems:
                failed[profile] = problems
            else:
                out[profile] = got[profile]
                how["model"] += 1
        if failed and reply:
            again = await ask(
                self.agent,
                json.dumps(
                    {
                        "languages": {lang: name},
                        "captions": {p: job.variants[p] for p in failed},
                        "verifier_rejected_previous_translation_because": failed,
                    }
                ),
            )
            retry = _by_lang(again, lang, name)
            for profile in list(failed):
                if not self._bad(job, profile, retry.get(profile)):
                    out[profile] = retry[profile]
                    how["retry"] += 1
                    del failed[profile]
        if failed:
            texts = [
                x for p in failed for x in (job.variants[p]["headline"], job.variants[p]["line"])
            ]
            machine = await translator.translate(texts, lang)
            for k, profile in enumerate(list(failed)):
                if machine:
                    t = {"headline": machine[2 * k], "line": machine[2 * k + 1]}
                    if not self._bad(job, profile, t):
                        out[profile] = t
                        how["translator"] += 1
                        del failed[profile]
                        continue
        for profile in failed:
            out[profile] = job.variants[profile]  # an unchecked line never airs; English does
            how["english"] += 1
        return out, how


def _by_lang(reply: dict | None, lang: str, name: str) -> dict:
    """Models sometimes key the reply by language name ('Hindi') instead of code ('hi')."""
    tr = (reply or {}).get("translations") or {}
    for key in (lang, name, name.lower()):
        if isinstance(tr.get(key), dict):
            return tr[key]
    if len(tr) == 1 and isinstance(next(iter(tr.values())), dict):
        return next(iter(tr.values()))
    return {}


def headline_for(m: Moment, clubs: dict[str, str], names: dict[str, str] | None = None) -> str:
    player_name = (names or {}).get(m.player or "", "").split(" ")[-1]
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
        "around_the_league": "Around the league",
        "player_spotlight": f"Spotlight on {player_name}",
        "great_save": "What a save",
        "half_time_recap": "Half-time",
        "full_time_recap": "Full-time",
        "match_preview": "Kick-off",
        "match_pulse": "State of play",
    }.get(m.type, m.type.replace("_", " ").title())


def build_agents(client: Any, tools: list, deep_client: Any = None) -> dict[str, Agent | None]:
    if client is None:
        return dict.fromkeys(
            ("director", "analyst", "narrator", "persona", "linguist", "league_director")
        )
    return {
        "director": Agent(client, prompts.DIRECTOR, name="Director"),
        "analyst": Agent(deep_client or client, prompts.ANALYST, name="Analyst", tools=tools),
        "narrator": Agent(client, prompts.NARRATOR, name="Narrator"),
        "persona": Agent(client, prompts.PERSONA, name="Persona"),
        "linguist": Agent(client, prompts.LINGUIST, name="Linguist"),
        "league_director": Agent(client, prompts.LEAGUE_DIRECTOR, name="LeagueDirector"),
    }


def build_workflow(agents: dict[str, Agent | None]):
    director = DirectorExec(agents["director"])
    analyst = AnalystExec(agents["analyst"])
    narrator = NarratorExec(agents["narrator"])
    verifier = VerifierExec(can_retry=agents["narrator"] is not None)
    critic = CriticExec(can_retry=agents["narrator"] is not None)
    template = TemplateExec()
    persona = PersonaExec(agents["persona"])
    linguist = LinguistExec(agents["linguist"])
    return (
        WorkflowBuilder(
            name="pitchside",
            start_executor=director,
            max_iterations=200,
            output_from=[linguist],
            intermediate_output_from=[persona],
        )
        .add_edge(director, analyst)
        .add_edge(analyst, narrator)
        .add_edge(narrator, verifier)
        .add_switch_case_edge_group(
            verifier,
            [
                Case(lambda j: j.status == "retry", narrator),
                Case(lambda j: j.status == "fallback", template),
                Default(critic),
            ],
        )
        .add_switch_case_edge_group(
            critic,
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
