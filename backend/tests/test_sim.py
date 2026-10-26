import statistics
from collections import Counter

import pytest

from pitchside.sim.engine import expected_goals, simulate
from pitchside.sim.roster import kingsport_city, riverside_athletic


def test_same_seed_same_match():
    assert simulate(7) == simulate(7)


def test_different_seeds_differ():
    assert simulate(7) != simulate(8)


def test_rosters_are_stable_and_unique():
    for club in (kingsport_city(), riverside_athletic()):
        assert len(club.players) == 16
        assert len({p.name for p in club.players}) == 16
    assert [p.name for p in kingsport_city().players] == [p.name for p in kingsport_city().players]


def test_events_are_ordered_and_well_formed():
    events = simulate(3)
    assert events[0]["type"] == "match_start" and events[-1]["type"] == "match_end"
    assert [e["event_id"] for e in events] == list(range(1, len(events) + 1))
    times = [e["t_ms"] for e in events]
    assert times == sorted(times)
    for e in events:
        if "x" in e:
            assert 0 <= e["x"] <= 105 and 0 <= e["y"] <= 68


def test_score_matches_goal_events():
    events = simulate(11)
    goals = Counter(e["team"] for e in events if e["type"] == "goal")
    assert events[-1]["data"]["score"] == {"KSC": goals["KSC"], "RVA": goals["RVA"]}


def test_xg_is_higher_close_to_goal():
    assert (
        expected_goals(99, 34, False, False)
        > expected_goals(88, 34, False, False)
        > expected_goals(80, 10, False, False)
    )
    assert expected_goals(94, 34, True, False) < expected_goals(94, 34, False, False)


@pytest.mark.parametrize("seed_range", [range(1, 21)])
def test_matches_look_like_football(seed_range):
    """Averages over 20 seeds stay inside rough real-world ranges."""
    goals, completion, shots, fouls, minutes = [], [], [], [], []
    for seed in seed_range:
        events = simulate(seed)
        c = Counter(e["type"] for e in events)
        passes = [e for e in events if e["type"] == "pass"]
        goals.append(c["goal"])
        completion.append(sum(e["outcome"] == "complete" for e in passes) / len(passes))
        shots.append(c["shot"])
        fouls.append(c["foul"])
        minutes.append(events[-1]["t_ms"] / 60000)
    assert 2.0 <= statistics.mean(goals) <= 4.0
    assert 0.76 <= statistics.mean(completion) <= 0.88
    assert 18 <= statistics.mean(shots) <= 32
    assert 14 <= statistics.mean(fouls) <= 30
    assert 92 <= statistics.mean(minutes) <= 101


def test_demo_seed_tells_the_comeback_story():
    events = simulate(16, "comeback")
    goals = [(e["minute"], e["team"]) for e in events if e["type"] == "goal"]
    assert goals[0][1] == "RVA"
    assert events[-1]["data"]["score"] == {"KSC": 2, "RVA": 1}
