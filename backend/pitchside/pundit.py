"""Ask Pitchside: a viewer's question, answered by the Pundit agent and checked by the Verifier and the Critic."""

from __future__ import annotations

import asyncio
import json
import time

from agent_framework import Agent

from pitchside import safety
from pitchside.agents import prompts
from pitchside.agents.critic import check_reasons
from pitchside.agents.pipeline import ask
from pitchside.agents.verify import (
    check_citations,
    check_language,
    check_leader,
    check_names,
    check_numbers,
    check_real_world,
    check_style,
)
from pitchside.stats.state import MatchState
from pitchside.tools import StatsTools


async def answer(
    state: MatchState, client, question: str, lang: str = "en", profile: str = "casual"
) -> dict:
    tools = StatsTools(state)
    agent = Agent(client, prompts.PUNDIT, name="Pundit", tools=tools.agent_tools())
    sheet = tools.fact_sheet(list(state.names))
    steps: list[dict] = []
    request = {
        "question": question[:300],
        "answer_in": prompts.LANGUAGES.get(lang, "English"),
        "viewer": profile,
        "match_minute_now": f"{state.minute} of 90",
        "score": state.score_line(),
        # Ground truth the answer must agree with: who scored and when, and who is who.
        "goals": [
            {"minute": e["minute"], "team": e["team"], "scorer": state.name(e["player"])}
            for e in state.events
            if e["type"] == "goal"
        ],
        "cards": [
            {
                "minute": e["minute"],
                "team": e["team"],
                "player": state.name(e["player"]),
                "card": e["card"],
            }
            for e in state.events
            if e["type"] == "card"
        ],
        "players": {name: pid for pid, name in state.names.items()},
        "clubs": {r: n for r, n in (getattr(state.league, "names", None) or {}).items()} or None,
    }
    clubs = {state.meta[s]["code"]: state.meta[s]["name"] for s in ("home", "away")}
    problems: list[str] = []
    for attempt in (1, 2):
        t0 = time.perf_counter()
        if problems:
            request["verifier_rejected_previous_answer_because"] = problems
        reply = await ask(agent, json.dumps(request))
        steps.append(
            {
                "agent": "pundit",
                "ms": round((time.perf_counter() - t0) * 1000),
                "status": "ok" if reply else "fallback",
                "note": f"draft {attempt}",
            }
        )
        if not reply or not reply.get("answer"):
            break
        t0 = time.perf_counter()
        # Citations we can't match are simply dropped; what must hold is every number in the answer.
        kept, _ = check_citations(reply.get("numbers", []), sheet, [])
        facts = {
            "cited": kept,
            "sheet": sheet,
            "truth": {k: request[k] for k in ("score", "goals", "match_minute_now")},
        }
        text = reply["answer"]
        problems = (
            check_numbers(text, facts)
            + check_names(text, {"players": list(state.names)}, state.names)
            + check_style(text, live=False)
            + check_language(text, lang)
            + check_real_world(text)
            + check_leader(text, dict(state.score))
        )
        if len(text.split()) < 5:
            problems.append("not an answer about the match")
        # The Critic reads English; answers in other languages get the number and name checks.
        reasons = check_reasons(text, sheet, clubs, minute=state.minute) if lang == "en" else []
        if reasons:
            steps.append(
                {"agent": "critic", "ms": 0, "status": "reject", "note": "; ".join(reasons[:2])}
            )
        problems += reasons
        steps.append(
            {
                "agent": "verifier",
                "ms": round((time.perf_counter() - t0) * 1000),
                "status": "pass" if not problems else "reject",
                "note": "; ".join(problems[:2]) or f"{len(kept)} numbers confirmed",
            }
        )
        if not problems:
            return {"answer": text, "verified": True, "evidence": kept, "steps": steps}
    return {
        "answer": "I can't answer that one from the match data. Ask me about the score, possession, pressing, a player or the league table.",
        "verified": False,
        "evidence": [],
        "steps": steps,
    }


async def screened_answer(
    state: MatchState, client, question: str, lang: str = "en", profile: str = "casual"
) -> dict:
    """Ask Pitchside as viewers get it: Content Safety and the Pundit start together, and a blocked
    question cancels the answer unseen."""
    answering = asyncio.create_task(answer(state, client, question, lang, profile))
    screened = await safety.screen(question)
    if not screened["ok"]:
        answering.cancel()
        reply = (
            "That sounds really hard. If you're struggling, please talk to someone you trust "
            "or a local helpline."
            if screened.get("category") == "SelfHarm"
            else "I'll stick to the football. Ask me about the match, a player or the table."
        )
        return {"answer": reply, "verified": False, "blocked": True, "steps": [screened["step"]]}
    result = await answering
    if screened["step"]:
        result["steps"] = [screened["step"], *result["steps"]]
    return result
