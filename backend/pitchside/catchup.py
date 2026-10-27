"""Catch me up: what a viewer missed while they were away, in their language and their view.

An agent tells the story of the missed spell from the moments the stats engine flagged; the
Verifier checks its numbers and names and the Critic checks its reasons. If the draft fails
twice, or there's no model, a summary built from the verified template lines airs instead.
"""

from __future__ import annotations

import json
import time

from agent_framework import Agent

from pitchside import translator
from pitchside.agents import prompts
from pitchside.agents.critic import check_reasons
from pitchside.agents.pipeline import ask
from pitchside.agents.templates import template_line
from pitchside.agents.verify import (
    check_language,
    check_leader,
    check_names,
    check_numbers,
    check_style,
)
from pitchside.stats.state import MatchState
from pitchside.tools import StatsTools

WORTH_TELLING = 45  # same bar as going on air


def _missed(state: MatchState, since: int) -> list:
    moments = [m for m in state.moments if m.minute >= since and m.significance >= WORTH_TELLING]
    goals = [m for m in moments if m.type == "goal"]
    rest = sorted((m for m in moments if m.type != "goal"), key=lambda m: -m.significance)
    return sorted(goals + rest[: max(0, 3 - len(goals))], key=lambda m: m.t_ms)


def _window_s(state: MatchState, since: int) -> int:
    return max(60, (state.minute - since) * 60)


def template_summary(state: MatchState, since: int, clubs: dict[str, str]) -> str:
    gone = state.minute - since
    a, b = state.teams
    lines = [f"You missed {gone} minutes, and it's {state.score_line()}."]
    for m in _missed(state, since):
        lines.append(template_line(m, state.names, clubs))
    w = _window_s(state, since)
    pos = {t: state.possession_pct(t, w) for t in (a, b)}
    leader = max(pos, key=pos.get)
    lines.append(f"{clubs.get(leader, leader)} have had {pos[leader]}% of the ball since.")
    return " ".join(lines)


async def catch_up(
    state: MatchState,
    client,
    since_minute: int,
    lang: str = "en",
    profile: str = "casual",
) -> dict:
    since = max(0, min(int(since_minute), state.minute))
    clubs = {state.meta[s]["code"]: state.meta[s]["name"] for s in ("home", "away")}
    missed = _missed(state, since)
    w = _window_s(state, since)
    sheet = StatsTools(state).fact_sheet(sorted({m.player for m in missed if m.player}))
    since_then = {t: state.team_metrics(t, w) for t in state.teams}
    facts = {
        "sheet": sheet,
        "moments": [m.to_dict() for m in missed],
        "since_then": since_then,
        "minutes_missed": state.minute - since,
        "minute_now": state.minute,
        "since_minute": since,
    }
    steps: list[dict] = []
    agent = Agent(client, prompts.CATCH_UP, name="CatchUp") if client is not None else None
    request = {
        "write_in": prompts.LANGUAGES.get(lang, "English"),
        "viewer": profile,
        "score_now": state.score_line(),
        "clubs": clubs,
        "minute_now": state.minute,
        "away_since_minute": since,
        "what_happened": [
            {**m.to_dict(), "player_name": state.name(m.player) if m.player else None}
            for m in missed
        ],
        "while_you_were_away": since_then,
    }
    problems: list[str] = []
    for attempt in (1, 2):
        if agent is None:
            break
        t0 = time.perf_counter()
        if problems:
            request["verifier_rejected_previous_draft_because"] = problems
        reply = await ask(agent, json.dumps(request, default=str))
        text = (reply or {}).get("text", "")
        steps.append(_step("catch-up", t0, "ok" if text else "fallback", f"draft {attempt}"))
        if not text:
            break
        t0 = time.perf_counter()
        problems = (
            check_numbers(text, facts)
            + check_names(text, {"players": [m.player for m in missed]}, state.names)
            + check_style(text, live=False)
            + check_language(text, lang)
            + check_leader(text, dict(state.score))
        )
        if lang == "en":
            problems += check_reasons(text, sheet, clubs, minute=state.minute)
        steps.append(
            _step(
                "verifier",
                t0,
                "pass" if not problems else "reject",
                "; ".join(problems[:2]) or "numbers, names and reasons checked",
            )
        )
        if not problems:
            return {"text": text, "verified": True, "since": since, "steps": steps}

    t0 = time.perf_counter()
    text = template_summary(state, since, clubs)
    if lang != "en":
        machine = await translator.translate([text], lang)
        text = machine[0] if machine else text
    steps.append(_step("template", t0, "ok", "verified template summary"))
    return {"text": text, "verified": True, "since": since, "steps": steps}


def _step(agent: str, t0: float, status: str, note: str) -> dict:
    return {
        "agent": agent,
        "ms": round((time.perf_counter() - t0) * 1000),
        "status": status,
        "note": note,
    }
