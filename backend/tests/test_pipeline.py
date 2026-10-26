import asyncio

from pitchside.runner import Broadcast
from pitchside.sim.engine import simulate


def run_match(**kw):
    async def go():
        return [item async for item in Broadcast(simulate(16, "comeback"), **kw).run()]

    return asyncio.run(go())


def test_templates_only_run_puts_verified_cards_on_air():
    items = run_match(profiles=["casual", "analyst"], langs=["en", "hi"])
    cards = [
        i["overlay"]
        for i in items
        if i["kind"] == "overlay" and i["overlay"]["type"] == "insight_card"
    ]
    traces = [i["trace"] for i in items if i["kind"] == "trace"]
    assert cards and traces
    assert all(c["provenance"]["verified"] for c in cards)
    assert {c["profile_key"] for c in cards} == {
        "casual:en",
        "analyst:en",
        "casual:hi",
        "analyst:hi",
    }
    goals = [
        c
        for c in cards
        if c["content"]["moment_type"] == "goal" and c["profile_key"] == "casual:en"
    ]
    assert len(goals) == 3


def test_every_aired_moment_passes_through_the_whole_graph():
    items = run_match()
    for t in (i["trace"] for i in items if i["kind"] == "trace"):
        agents = [s["agent"] for s in t["steps"]]
        assert agents[0] == "director" and agents[-1] == "linguist"
        assert (
            "verifier" in agents and "template" in agents
        )  # no model: verifier rejects, template fills


def test_overlays_start_after_their_moment():
    items = run_match()
    for o in (
        i["overlay"]
        for i in items
        if i["kind"] == "overlay" and i["overlay"]["type"] == "insight_card"
    ):
        assert o["start_t_ms"] >= o["anchor_t_ms"]


def test_live_mode_streams_events_while_agents_work_in_the_background():
    async def go():
        return [item async for item in Broadcast(simulate(16, "comeback")).run(speed=1e6)]

    items = asyncio.run(go())
    kinds = [i["kind"] for i in items]
    assert kinds.count("event") == len(simulate(16, "comeback"))
    assert kinds.count("trace") == len(run_match() and [i for i in run_match() if i["kind"] == "trace"])
