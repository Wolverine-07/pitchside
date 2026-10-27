import re

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
    good = c.post(
        "/api/verify", json={"match_key": "test", "text": "Riverside lead 1-0 through Pellello."}
    ).json()
    bad = c.post(
        "/api/verify",
        json={"match_key": "test", "text": "Riverside have had 99 shots and lead comfortably."},
    ).json()
    gone = c.post("/api/verify", json={"match_key": "missing", "text": "anything"}).json()
    assert good["ok"], good
    assert not bad["ok"] and any("99" in p for p in bad["problems"])
    assert not gone["ok"]
    LIVE.pop("test")


def test_catch_up_without_a_model_is_a_verified_template():
    LIVE["away"] = live_state(75)
    r = TestClient(app).post("/api/catchup", json={"match_key": "away", "since_minute": 60}).json()
    assert r["verified"] and r["since"] == 60
    assert r["text"].startswith("You missed") and "Velino" in r["text"]
    LIVE.pop("away")


def test_the_page_route_never_serves_files_outside_the_frontend():
    from pitchside import api

    if not api.STATIC.exists():
        import pytest

        pytest.skip("frontend not built")
    c = TestClient(app)
    for path in [
        "/..%2f..%2fbackend%2fpyproject.toml",
        "/%2e%2e/%2e%2e/backend/pyproject.toml",
        "/..%2f..%2f..%2f..%2f..%2f..%2f..%2fetc%2fhostname",
        "/..%2f..%2f..%2f..%2f..%2f..%2f..%2fproc%2fself%2fenviron",
    ]:
        r = c.get(path)
        assert r.status_code == 200 and r.text.lstrip().lower().startswith("<!doctype html"), path
    assert c.get("/favicon.svg").text.startswith("<svg")


def test_the_live_socket_streams_a_match_from_kick_off():
    # No lifespan here: the MCP session manager may start once per process (see the MCP test).
    with TestClient(app).websocket_connect("/ws/match?speed=60&langs=en&profiles=casual") as ws:
        hello = ws.receive_json()
        assert hello["kind"] == "hello" and hello["match_key"] in LIVE
        kinds, first_card = set(), None
        for _ in range(400):
            item = ws.receive_json()
            kinds.add(item["kind"])
            if item["kind"] == "overlay" and first_card is None:
                first_card = item["overlay"]
            if first_card and "event" in kinds and "snapshot" in kinds:
                break
        assert first_card["content"]["moment_type"] == "match_preview"
        assert first_card["profile_key"] in ("flash:en", "casual:en")
    assert hello["match_key"] not in LIVE  # the match is forgotten when the viewer leaves


def test_query_values_are_capped_and_cleaned():
    from pitchside.api import _langs, _list, _number

    assert _langs("hi,ar,ja,fr,de,xx,hi") == ["en", "hi", "ar", "ja"]
    assert _langs(None) == ["en"] and _langs("klingon") == ["en"]
    assert len(_list(",".join(f"p{i}" for i in range(50)), "casual")) == 5
    assert _list(",,,", "casual") == ["casual"]
    assert _number("abc", 10, 0.5, 60) == 10
    assert _number("nan", 10, 0.5, 60) == 10
    assert _number("1e9", 10, 0.5, 60) == 60 and _number("-5", 10, 0.5, 60) == 0.5


def test_bad_input_never_breaks_the_api():
    c = TestClient(app)
    assert c.get("/api/meta?storyline=nonsense").status_code == 200
    assert c.get("/api/meta?fixture=XXX-YYY").json()["home"]["code"] == "KSC"
    LIVE["bad"] = live_state(30)
    r = c.post("/api/catchup", json={"match_key": "bad", "since_minute": "soon"}).json()
    assert r["verified"] and r["since"] == 0
    assert c.post("/api/catchup", json={"match_key": "gone"}).json()["verified"] is False
    r = c.post("/api/ask", json={"match_key": "bad", "question": "Who is winning?"}).json()
    assert not r["verified"] and "template mode" in r["answer"]  # no model in tests
    assert (
        "isn't live"
        in c.post("/api/ask", json={"match_key": "gone", "question": "x"}).json()["answer"]
    )
    assert (
        c.get("/api/speak?text=hello").status_code == 503
    )  # no Speech key: the browser voice takes over
    LIVE.pop("bad")


def test_the_mcp_server_lists_the_stats_tools():
    with TestClient(app) as c:
        headers = {"accept": "application/json, text/event-stream"}
        init = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        }
        r = c.post("/mcp/", json=init, headers=headers)
        assert r.status_code == 200, r.text
        session = r.headers.get("mcp-session-id")
        if session:
            headers["mcp-session-id"] = session
        c.post(
            "/mcp/", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=headers
        )
        r = c.post(
            "/mcp/", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=headers
        )
        names = set(re.findall(r'"name":\s*"(\w+)"', r.text))
        assert {"match_snapshot", "team_metrics", "player_summary", "league_table"} <= names
