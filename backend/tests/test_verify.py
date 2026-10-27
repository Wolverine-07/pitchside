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


def test_recaps_may_mention_goal_minutes():
    from pitchside.agents.verify import verify

    facts = {
        "moment": {
            "minute": 90,
            "evidence": [{"metric": "goal_minute", "value": 68, "team": "KSC", "player": "KSC-09"}],
        }
    }
    assert verify("The goal in the 68th minute turned it", facts, {}, live=False)
    assert not verify("A goal in the 77th minute turned it", facts, {}, live=False)


def test_only_the_club_in_first_leads_the_table():
    from pitchside.agents.verify import check_table

    second = {"moment": {"evidence": [{"metric": "live_position", "value": 2, "team": "KSC"}]}}
    first = {"moment": {"evidence": [{"metric": "live_position", "value": 1, "team": "KSC"}]}}
    assert check_table("Kingsport City lead the table in second.", second)
    assert not check_table("Kingsport City lead the table.", first)
    assert not check_table("Kingsport sit second in the table.", second)


def test_who_leads_must_match_the_score():
    from pitchside.agents.verify import check_leader

    score = {"KSC": 0, "RVA": 1}
    assert check_leader("Kingsport are ahead thanks to Pellello's early goal", score)
    assert check_leader("Riverside trail at the hour", score)
    assert check_leader("Riverside lead 1-0 and Kingsport are chasing the game", score) == []
    assert check_leader("Kingsport lead in possession", score) == []  # not about the score
    assert check_leader("Coldharbour lead at Brightwater", score) == []  # another match


def test_a_club_that_has_not_scored_still_counts_for_who_leads():
    from collections import Counter

    from pitchside.agents.verify import check_leader
    from tests.test_api import live_state

    st = live_state(60)  # 0-1: the Counter has no entry for Kingsport at all
    assert "KSC" not in st.score
    assert check_leader("Kingsport are ahead", {t: st.score[t] for t in st.teams})
    assert (
        check_leader("Kingsport are ahead", dict(Counter({"RVA": 1}))) == []
    )  # why callers pass both


def test_scorelines_must_be_scores_the_match_has_been_at():
    from pitchside.agents.verify import check_scorelines

    goals, teams = ["RVA", "KSC", "KSC"], ["KSC", "RVA"]  # 0-0, 0-1, 1-1, 2-1
    ok = [
        "Kingsport lead 2-1 after the comeback.",
        "Riverside trail 1-2 now.",
        "Riverside went 1-0 up early on.",
        "Kingsport 1-1 Riverside at one stage.",
        "Ashvale lead Dunmore 3-0 elsewhere.",  # another match: not this one's to check
        "It finished 4-4 in the other game.",  # no club of this match named
    ]
    ok += [
        "Kingsport were behind, and Ashvale won 3-0 at Dunmore.",  # nearest club is in another match
        "A 1-0 win for Riverside would have been the story.",
        "Kingsport pressed hardest in the 60-70th minute spell.",  # not a score
    ]
    bad = [
        "Riverside lead 3-0.",
        "Kingsport are 2-0 up.",
        "KSC 0-2 RVA",
        "Kingsport scored 4 goals while you were away and lead 4-1.",
        "It ended in a 3-1 win for Kingsport.",
    ]
    for text in ok:
        assert check_scorelines(text, goals, teams) == [], text
    for text in bad:
        assert check_scorelines(text, goals, teams), text


def test_nobody_is_sent_off_without_a_red_card():
    from pitchside.agents.verify import check_cards

    yellow = [{"player": "Ari Wexavi", "card": "yellow"}]
    for text in [
        "Pellello was sent off just before the break.",
        "Riverside are down to ten men.",
        "Wexavi saw red for that challenge.",
    ]:
        assert check_cards(text, yellow), text
    for text in [
        "Pellello hasn't been sent off; he's still on the pitch.",
        "There has been no red card in this match.",
        "Nobody has been sent off, but Wexavi is on a yellow.",
        "Wexavi was booked, not sent off.",
    ]:
        assert check_cards(text, yellow) == [], text
    assert check_cards("Wexavi was sent off.", [{"player": "Ari Wexavi", "card": "red"}]) == []


def test_real_world_and_language_checks():
    from pitchside.agents.verify import check_language, check_real_world

    for text in ["They play like Arsenal.", "A Premier League side would", "Man United did that"]:
        assert check_real_world(text), text
    assert check_real_world("Kingsport City and Riverside Athletic in The Coastal League") == []
    assert check_language("रिवरसाइड आगे है", "hi") == []
    assert check_language("Riverside lead", "hi")
    assert check_language("ريفرسايد في المقدمة", "ar") == []
    assert check_language("リバーサイドがリード", "ja") == []
    assert (
        check_language("Riverside mène 1-0", "fr") == []
    )  # Latin-script languages aren't script-checked
