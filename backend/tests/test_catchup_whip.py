"""Catch me up and the whip-around with scripted agents: what airs is always checked, whatever the model says.

Catch-up: away from 60' to 75' of the demo match, Kingsport came from 0-1 to 2-1 (Wexavi 68', Velino 71').
"""

import asyncio
import json
from dataclasses import replace

import pytest

from pitchside import catchup, whip
from pitchside.sim.league import LeagueState, clubs, matchday
from tests.test_api import live_state

GOOD = "Kingsport turned it round while you were away: Wexavi and then Velino scored, and it's 2-1 now."


@pytest.fixture(scope="module")
def state():
    return live_state(75)


@pytest.fixture
def model(monkeypatch):
    seen: list[dict] = []
    drafts: list = []

    async def fake_ask(agent, prompt):
        seen.append(json.loads(prompt))
        return drafts.pop(0) if drafts else None

    monkeypatch.setattr(catchup, "Agent", lambda *a, **k: object())
    monkeypatch.setattr(catchup, "ask", fake_ask)
    return drafts, seen


MODEL = object()


def catch_up(state, since=60, lang="en", client=MODEL):
    return asyncio.run(catchup.catch_up(state, client, since, lang))


def test_a_true_summary_airs_as_written(state, model):
    drafts, seen = model
    drafts.append({"text": GOOD})
    r = catch_up(state)
    assert r["verified"] and r["text"] == GOOD and r["since"] == 60
    told = [(m["type"], m["player_name"]) for m in seen[0]["what_happened"]]
    assert ("goal", "Ari Wexavi") in told and ("goal", "Tavi Velino") in told
    assert seen[0]["score_now"] == "KSC 2-1 RVA"


@pytest.mark.parametrize(
    "bad",
    [
        "Kingsport scored 4 goals while you were away and lead 4-1.",  # invented scoreline
        "Riverside are ahead after Pellello's second goal.",  # wrong leader
        "Kingsport came back to lead 2-1, and Riverside are down to ten men.",  # no red card
        "Like Arsenal, Kingsport turned it round and lead 2-1 now.",  # a real club
        "Kingsport lead 2-1!! 🔥🔥",  # style
    ],
)
def test_a_bad_draft_is_sent_back_then_replaced_by_the_template(state, model, bad):
    drafts, seen = model
    drafts += [{"text": bad}, {"text": bad}]
    r = catch_up(state)
    assert r["verified"] and r["text"].startswith("You missed 15 minutes, and it's KSC 2-1 RVA.")
    assert seen[1]["verifier_rejected_previous_draft_because"]
    assert [s["agent"] for s in r["steps"]] == [
        "catch-up",
        "verifier",
        "catch-up",
        "verifier",
        "template",
    ]


def test_the_second_draft_airs_when_it_fixes_the_first(state, model):
    drafts, _ = model
    drafts += [{"text": "Kingsport lead 3-1 now."}, {"text": GOOD}]
    r = catch_up(state)
    assert r["text"] == GOOD


def test_a_summary_in_the_wrong_script_is_rejected(state, model):
    drafts, _ = model
    drafts += [{"text": GOOD}, {"text": GOOD}]
    r = catch_up(state, lang="hi")
    # No translator in tests, so the verified English template airs rather than unchecked English.
    assert r["text"].startswith("You missed")


def test_the_since_minute_is_clamped(state, model):
    assert catch_up(state, since=200, client=None)["since"] == state.minute
    assert catch_up(state, since=-10, client=None)["since"] == 0


def test_the_template_names_every_goal_missed(state):
    names = {"KSC": "Kingsport City", "RVA": "Riverside Athletic"}
    text = catchup.template_summary(state, 60, names)
    assert "Ari Wexavi scores" in text and "Tavi Velino scores" in text
    assert "Pellello" not in text  # his goal was at 5', before the viewer left
    assert catchup.template_summary(state, 0, names).count(" scores") == 3


# Whip-around


@pytest.fixture(scope="module")
def league_goal():
    fixtures = matchday(16, "comeback")
    f = next(f for f in fixtures[1:] if any(e["type"] == "goal" for e in f.events))
    i = next(i for i, e in enumerate(f.events) if e["type"] == "goal")
    f = replace(f, score={f.home: 0, f.away: 0})
    f.score[f.events[i]["team"]] += 1
    all_clubs = clubs()
    names = {c: k.name for c, k in all_clubs.items()}
    colors = {c: k.colors[0] for c, k in all_clubs.items()}
    return whip.candidate(f, i, names, colors, []), f


def test_the_replay_is_the_scoring_side_moving_to_the_right_goal(league_goal):
    cand, f = league_goal
    path = cand["path"]
    assert 2 <= len(path) <= whip.BUILD_UP + 1
    assert {p["team"] for p in path} == {cand["team"]}
    assert path[-1] == {
        "x": 105 if cand["team"] == f.home else 0,
        "y": 34,
        "team": cand["team"],
        "type": "goal",
    }
    assert all(0 <= p["x"] <= 105 and 0 <= p["y"] <= 68 for p in path)
    roster = {p.name for p in clubs()[cand["team"]].players}
    assert cand["scorer"] in roster


def _ctx(**kw):
    base = {
        "minute": 30,
        "score": "KSC 0-1 RVA",
        "shots_in_last_30_seconds": 0,
        "goal_in_last_minute": False,
        "attack_in_final_third": False,
        "team_on_the_ball": "KSC",
    }
    return {**base, **kw}


HERE = {"KSC": "Kingsport City", "RVA": "Riverside Athletic"}


def test_the_rule_never_cuts_away_from_danger(league_goal):
    cand, _ = league_goal
    assert whip.rule(cand, _ctx(), HERE)[0]
    assert not whip.rule(cand, _ctx(goal_in_last_minute=True), HERE)[0]
    assert not whip.rule(cand, _ctx(shots_in_last_30_seconds=1), HERE)[0]
    cut, why = whip.rule(cand, _ctx(attack_in_final_third=True), HERE)
    assert not cut and "Kingsport City" in why


@pytest.mark.parametrize(
    ("reply", "how"),
    [
        ({"cut": True, "reason": "Nothing on here, so over to the goal elsewhere."}, "agent"),
        ({"cut": False, "reason": "Kingsport are in the box, so we stay."}, "agent"),
        (
            {"cut": True, "reason": "Over there, where they've had 37 shots."},
            "fallback",
        ),  # invented
        ({"cut": "yes", "reason": "Cut!"}, "fallback"),  # not a bool
        ({"cut": True}, "fallback"),  # no reason to show
        (None, "fallback"),  # timeout or bad JSON
    ],
)
def test_the_director_is_trusted_only_when_its_reason_checks_out(
    monkeypatch, league_goal, reply, how
):
    cand, _ = league_goal

    async def fake_ask(agent, prompt):
        sent = json.loads(prompt)
        assert "path" not in sent["goal_elsewhere"]  # the agent decides, it doesn't draw
        return reply

    monkeypatch.setattr(whip, "ask", fake_ask)
    cut, reason, decided_by, _ = asyncio.run(whip.decide(object(), cand, _ctx(), HERE))
    assert decided_by == how and reason
    if how == "agent":
        assert (cut, reason) == (reply["cut"], reply["reason"])
    else:
        assert (cut, reason) == whip.rule(cand, _ctx(), HERE)


def test_without_a_model_the_rule_decides(league_goal):
    cand, _ = league_goal
    assert asyncio.run(whip.decide(None, cand, _ctx(), HERE))[2] == "rule"


def test_featured_context_reads_the_live_match():
    ctx = whip.featured_context(live_state(1))
    assert ctx["minute"] == 1 and ctx["score"] == "KSC 0-0 RVA"
    assert not ctx["goal_in_last_minute"]
    after_goal = live_state(6)  # Pellello scored at 5'
    assert any(e["type"] == "goal" for e in after_goal.events)
    assert isinstance(whip.featured_context(after_goal)["attack_in_final_third"], bool)


def test_league_state_tracks_every_fixture():
    fixtures = matchday(16, "comeback")
    assert len(fixtures) == 4 and len({c for f in fixtures for c in (f.home, f.away)}) == 8
    names = {c: k.name for c, k in clubs().items()}
    league = LeagueState(fixtures, names, {c: "#000" for c in names})
    assert league is not None
