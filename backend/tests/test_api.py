from fastapi.testclient import TestClient

from pitchside.api import LIVE, app
from pitchside.sim.engine import simulate
from pitchside.stats.state import MatchState


def live_state(until_minute: int) -> MatchState:
    st = MatchState()
    for e in simulate(16, "comeback"):
        st.ingest(e)
        if e["minute"] >= until_minute:
            break
    return st


def test_health_and_meta_include_the_league():
    c = TestClient(app)
    assert c.get("/api/health").json()["ok"]
    meta = c.get("/api/meta").json()
    assert meta["league"]["league"] == "The Coastal League"
    assert len(meta["league"]["table"]) == 8
    assert len(meta["fixtures"]) == 4


def test_studio_edits_are_verified_against_the_live_match():
    LIVE["test"] = live_state(20)
    c = TestClient(app)
    good = c.post("/api/verify", json={"match_key": "test", "text": "Riverside lead 1-0 through Pellello."}).json()
    bad = c.post("/api/verify", json={"match_key": "test", "text": "Riverside have had 99 shots and lead comfortably."}).json()
    gone = c.post("/api/verify", json={"match_key": "missing", "text": "anything"}).json()
    assert good["ok"], good
    assert not bad["ok"] and any("99" in p for p in bad["problems"])
    assert not gone["ok"]
    LIVE.pop("test")
