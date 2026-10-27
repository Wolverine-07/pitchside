"""Whip-around: the League Director decides when to cut away to a goal at another ground.

Like a live multi-match show, a goal elsewhere can take the picture for a few seconds, but
not while something is about to happen in the featured match. The League Director agent
weighs the two; its reason goes on screen, so its numbers are checked like any caption. With
no model (or a bad reply) a rule decides: cut unless the featured match is dangerous right now.
"""

from __future__ import annotations

import json
import time
from functools import lru_cache

from pitchside.agents.pipeline import ask
from pitchside.agents.verify import check_numbers, check_style
from pitchside.sim.league import Fixture, clubs
from pitchside.stats.state import ON_BALL, MatchState

BUILD_UP = 8  # touches shown in the replay


@lru_cache(maxsize=1)
def _names() -> dict[str, str]:
    return {p.id: p.name for c in clubs().values() for p in c.players}


def candidate(
    f: Fixture,
    goal_index: int,
    names: dict[str, str],
    colors: dict[str, str],
    moved: list[str],
) -> dict:
    """A goal elsewhere as a cut the viewer could see: score, scorer and the build-up path."""
    goal = f.events[goal_index]
    team = goal["team"]
    path = []
    for e in reversed(f.events[:goal_index]):
        if e["type"] not in ON_BALL or e.get("x") is None:
            continue
        if e.get("team") != team:
            break
        x, y = (e["x"], e["y"]) if team == f.home else (105 - e["x"], 68 - e["y"])
        path.insert(0, {"x": x, "y": y, "team": team, "type": e["type"]})
        if len(path) == BUILD_UP:
            break
    path.append({"x": 105 if team == f.home else 0, "y": 34, "team": team, "type": "goal"})
    return {
        "id": f"cut-{f.id}-{goal['event_id']}",
        "fixture": f.id,
        "home": {"code": f.home, "name": names[f.home], "color": colors[f.home]},
        "away": {"code": f.away, "name": names[f.away], "color": colors[f.away]},
        "score": dict(f.score),
        "minute": goal.get("minute", f.minute),
        "team": team,
        "scorer": _names().get(goal.get("player", ""), ""),
        "path": path,
        "moves_featured_clubs": moved,
    }


def featured_context(state: MatchState) -> dict:
    """What's happening in the featured match right now, from the stats engine."""
    now = state.t_ms
    recent = [e for e in state.events if e["t_ms"] >= now - 30_000]
    on_ball = [e for e in state.events[-40:] if e["type"] in ON_BALL and e.get("x") is not None]
    last = on_ball[-1] if on_ball else None
    return {
        "minute": state.minute,
        "score": state.score_line(),
        "shots_in_last_30_seconds": sum(e["type"] == "shot" for e in recent),
        "goal_in_last_minute": any(
            e["type"] == "goal" and e["t_ms"] >= now - 60_000 for e in state.events[-200:]
        ),
        # Events use the acting team's attacking direction: x near 105 is near the goal they attack.
        "attack_in_final_third": bool(last and last["x"] >= 70),
        "team_on_the_ball": last.get("team") if last else None,
    }


def rule(cand: dict, ctx: dict, clubs_now: dict[str, str]) -> tuple[bool, str]:
    where = f"{cand['home']['name']} {cand['score'][cand['home']['code']]}-{cand['score'][cand['away']['code']]} {cand['away']['name']}"
    if ctx["goal_in_last_minute"]:
        return False, f"Staying here after the goal; {where} comes up in the round-up."
    if ctx["shots_in_last_30_seconds"] or ctx["attack_in_final_third"]:
        team = clubs_now.get(ctx["team_on_the_ball"] or "", "the attack")
        return False, f"Staying with {team} in the final third; {where} can wait."
    return True, f"Quiet here, so over to {where}."


async def decide(
    agent, cand: dict, ctx: dict, clubs_now: dict[str, str]
) -> tuple[bool, str, str, int]:
    """(cut, reason, how, ms). how is "agent", "rule" or "fallback"."""
    t0 = time.perf_counter()
    reply = await ask(
        agent,
        json.dumps(
            {
                "goal_elsewhere": {k: v for k, v in cand.items() if k != "path"},
                "featured_match": {**ctx, "clubs": clubs_now},
            }
        ),
    )
    ms = round((time.perf_counter() - t0) * 1000)
    if reply and isinstance(reply.get("cut"), bool) and reply.get("reason"):
        facts = {"cand": {k: v for k, v in cand.items() if k != "path"}, "ctx": ctx}
        reason = str(reply["reason"])
        if not check_numbers(reason, facts) and not check_style(reason):
            return reply["cut"], reason, "agent", ms
    cut, reason = rule(cand, ctx, clubs_now)
    return cut, reason, "fallback" if agent else "rule", ms
