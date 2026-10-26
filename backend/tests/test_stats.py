from collections import Counter

import pytest

from pitchside.sim.engine import simulate
from pitchside.stats.metrics import chaos_index, pass_difficulty, threat
from pitchside.stats.state import MatchState


@pytest.fixture(scope="module")
def demo() -> MatchState:
    st = MatchState()
    for e in simulate(16, "comeback"):
        st.ingest(e)
    return st


def test_threat_rises_towards_goal():
    assert threat(100, 34) > threat(80, 34) > threat(40, 34)
    assert threat(95, 34) > threat(95, 2)


def test_pass_difficulty_orders_sensibly():
    easy = {"x": 40, "y": 34, "end_x": 48, "end_y": 34, "length_m": 8}
    hard = {
        "x": 60,
        "y": 10,
        "end_x": 95,
        "end_y": 30,
        "length_m": 40,
        "under_pressure": True,
        "tags": ["cross"],
    }
    assert 0 <= pass_difficulty(easy) < 30
    assert 70 < pass_difficulty(hard) <= 100


def test_chaos_index_bounds():
    assert chaos_index(0, 60, 0) == 0.0
    assert chaos_index(10, 0, 10) == 1.0


def test_score_and_goals_agree_with_events(demo):
    assert demo.snapshot()["score"] == {"KSC": 2, "RVA": 1}
    assert sum(m.type == "goal" for m in demo.moments) == 3


def test_possession_adds_up(demo):
    pct = demo.snapshot()["possession_pct"]
    assert 98 <= pct["KSC"] + pct["RVA"] <= 102


def test_player_summary_matches_raw_events(demo):
    events = demo.events
    pid = "KSC-09"
    passes = [e for e in events if e["type"] == "pass" and e.get("player") == pid]
    s = demo.player_summary(pid)
    assert s["passes"] == len(passes)
    assert s["goals"] == sum(e["type"] == "goal" and e["player"] == pid for e in events)


def test_every_moment_has_evidence_and_a_valid_significance(demo):
    for m in demo.moments:
        assert m.evidence, m
        assert 0 < m.significance <= 100


def test_demo_has_a_kingsport_pressing_spell_before_the_equaliser(demo):
    equaliser = next(m for m in demo.moments if m.type == "goal" and m.team == "KSC")
    spells = [m for m in demo.moments if m.type == "pressing_spell" and m.team == "KSC"]
    assert any(0 < equaliser.t_ms - m.t_ms < 6 * 60_000 for m in spells)


def test_moment_volume_is_watchable(demo):
    counts = Counter(m.type for m in demo.moments)
    assert counts["momentum_swing"] <= 15
    assert len(demo.moments) <= 100
