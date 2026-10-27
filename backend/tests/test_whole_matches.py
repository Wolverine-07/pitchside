"""Whole matchdays on seeds other than the demo one: what airs must hold up on any match, not just seed 16."""

import asyncio

import pytest

from pitchside.agents.verify import check_leader, check_real_world, check_scorelines, check_style
from pitchside.runner import Broadcast
from pitchside.sim.league import LeagueState, clubs, matchday

SEEDS = [3, 11, 27, 58]


def run(seed):
    fixtures = matchday(seed, "none")
    all_clubs = clubs()
    league = LeagueState(
        fixtures,
        {c: k.name for c, k in all_clubs.items()},
        {c: k.colors[0] for c, k in all_clubs.items()},
    )
    events = fixtures[0].events
    home, away = fixtures[0].home, fixtures[0].away

    async def go():
        b = Broadcast(events, None, ["casual", "analyst", f"club:{away}"], ["en"], league=league)
        return [item async for item in b.run()]

    return events, (home, away), asyncio.run(go())


@pytest.fixture(scope="module", params=SEEDS)
def match(request):
    return run(request.param)


def test_every_caption_tells_the_truth_about_the_score(match):
    events, teams, items = match
    goals = [e for e in events if e["type"] == "goal"]
    cards = [
        i["overlay"]
        for i in items
        if i["kind"] == "overlay" and i["overlay"]["type"] == "insight_card"
    ]
    assert cards
    for c in cards:
        text = f"{c['content']['headline']}. {c['content']['body']}"
        scored = [g["team"] for g in goals if g["t_ms"] <= c["anchor_t_ms"]]
        score = {t: scored.count(t) for t in teams}
        assert c["provenance"]["verified"], text
        assert check_real_world(text) == [], text
        assert check_style(text, live=False) == [], text
        assert check_leader(text, score) == [], (text, score)
        assert check_scorelines(text, scored, list(teams)) == [], (text, scored)


def test_every_goal_goes_out_at_once_and_the_final_score_adds_up(match):
    events, teams, items = match
    goals = [e for e in events if e["type"] == "goal"]
    flashes = [
        i["overlay"]
        for i in items
        if i["kind"] == "overlay"
        and i["overlay"]["profile_key"] == "flash:en"
        and i["overlay"]["content"]["moment_type"] == "goal"
    ]
    assert len(flashes) == len(goals)
    last = [i["snapshot"] for i in items if i["kind"] == "snapshot"][-1]
    assert last["score"] == {t: sum(g["team"] == t for g in goals) for t in teams}


def test_every_view_gets_captions_and_the_stream_moves_forward(match):
    _, teams, items = match
    keys = {i["overlay"]["profile_key"] for i in items if i["kind"] == "overlay"}
    assert {"casual:en", "analyst:en", f"club:{teams[1]}:en"} <= keys
    times = [i["event"]["t_ms"] for i in items if i["kind"] == "event"]
    assert times == sorted(times)
