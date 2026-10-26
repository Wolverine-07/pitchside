from pitchside.agents.templates import template_line
from pitchside.agents.verify import check_names, check_numbers, check_style, numbers_in, verify
from pitchside.sim.engine import simulate
from pitchside.stats.state import MatchState

FACTS = {
    "moment": {
        "minute": 64,
        "team": "KSC",
        "evidence": [{"metric": "high_regains", "value": 3, "window_s": 90}],
    },
    "metrics": {"ppda": 8.4, "pass_accuracy_under_pressure_pct": 61, "chaos": 0.62},
    "players": ["KSC-09"],
}
ROSTER = {"KSC-09": "Ari Wexavi", "RVA-04": "Bram Corley"}


def test_numbers_in_reads_digits_ordinals_and_words():
    assert numbers_in("three regains in 90 seconds, 64th minute, 61%") == [90.0, 64.0, 61.0, 3.0]


def test_true_numbers_pass():
    line = "Kingsport win it back three times in 90 seconds. Riverside are completing 61% under pressure."
    assert check_numbers(line, FACTS) == []


def test_restated_numbers_pass():
    assert (
        check_numbers("A chaos index of 62 per cent, the press is on for 2 minutes now", FACTS)
        == []
    )
    assert check_numbers("PPDA down to 8.4", FACTS) == []


def test_invented_number_fails():
    problems = check_numbers("Four regains in 90 seconds", FACTS)
    assert problems and "4" in problems[0]


def test_wrong_player_fails_and_right_player_passes():
    assert check_names("Wexavi again, winning it back", FACTS, ROSTER) == []
    assert check_names("Corley is caught out", FACTS, ROSTER)


def test_style_rules():
    assert check_style("Kingsport turn the screw.") == []
    assert check_style("This is a testament to their press")
    assert check_style("What a press!! 🔥")
    assert check_style(" ".join(["word"] * 40))


def test_template_lines_always_verify():
    st = MatchState()
    for e in simulate(16, "comeback"):
        st.ingest(e)
    clubs = {"KSC": "Kingsport City", "RVA": "Riverside Athletic"}
    for m in st.moments:
        facts = {"moment": m.to_dict(), "score": st.score_line()}
        line = template_line(m, st.names, clubs)
        result = verify(line, facts, st.names)
        assert result, (line, result.problems)


def test_context_checks_catch_common_model_mistakes():
    from pitchside.agents.verify import check_context

    assert check_context("Frantic finish as play breaks down", 10)
    assert not check_context("Frantic finish as play breaks down", 88)
    assert check_context("Kingsport wins it back again", 64)
    assert not check_context("Kingsport win it back again", 64)


def test_minute_references_must_match_the_moment():
    from pitchside.agents.verify import check_context

    assert check_context("Riverside take control after the half-hour", 53)
    assert not check_context("Riverside take control after the half-hour", 33)
    assert check_context("Wexavi scores at 68 minutes", 68)
    assert not check_context("Wexavi scores in the 68th minute", 68)
    assert check_context("Wexavi scores in the 70th minute", 68)


def test_audience_checks_keep_jargon_for_analysts():
    from pitchside.agents.verify import check_audience

    line = "Riverside press at 8.3 PPDA with 92% passing and 6.7 passes a minute"
    assert check_audience(line, "casual")
    assert check_audience(line, "player:KSC-09")
    assert not check_audience(line, "analyst")
    assert not check_audience("Riverside press hard and keep 92% of their passes", "casual")


def test_late_is_only_allowed_late_in_the_match():
    from pitchside.agents.verify import check_context

    assert check_context("Late scramble on the pitch", 62)
    assert not check_context("Late scramble on the pitch", 86)
    assert not check_context("A late tackle stops the break", 20)
