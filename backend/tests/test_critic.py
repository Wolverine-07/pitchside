import pytest

from pitchside.agents.critic import CHAOTIC, SHORT, check_reasons
from pitchside.agents.pipeline import headline_for
from pitchside.agents.templates import template_line
from pitchside.sim.engine import simulate
from pitchside.stats.state import MatchState
from pitchside.tools import StatsTools

CLUBS = {"KSC": "Kingsport City", "RVA": "Riverside Athletic"}


@pytest.fixture(scope="module")
def sheets():
    """The fact sheet after every moment of the demo match, as the agents would see it."""
    st = MatchState()
    out = []
    for e in simulate(16, "comeback"):
        for m in st.ingest(e):
            out.append((m, StatsTools(st).fact_sheet([]), st.names))
    return out


def _high(sheet, team):
    return max(sheet["metrics"][team][w]["high_regains"] for w in SHORT)


def test_pressing_must_show_in_the_numbers(sheets):
    quiet = next(s for m, s, _ in sheets if m.minute > 10 and _high(s, "RVA") < 2)
    problems = check_reasons("Riverside press Kingsport high up the pitch.", quiet, CLUBS)
    assert problems and "press" in problems[0]
    busy = next(s for m, s, _ in sheets if _high(s, "KSC") >= 2)
    assert check_reasons("Kingsport press high and Riverside can't cope.", busy, CLUBS) == []


def test_the_reason_belongs_to_the_club_named_before_it(sheets):
    s = next(s for _, s, _ in sheets if _high(s, "KSC") >= 2 and _high(s, "RVA") < 2)
    assert check_reasons("Kingsport press Riverside into mistakes.", s, CLUBS) == []
    assert check_reasons("Riverside press Kingsport into mistakes.", s, CLUBS)
    assert check_reasons("Kingsport are pressed by Riverside.", s, CLUBS)


def test_chaos_needs_a_chaotic_game(sheets):
    calm = next(s for m, s, _ in sheets if max(s["chaos"][w] for w in SHORT) < CHAOTIC)
    assert check_reasons("A frantic, scrappy spell.", calm, CLUBS)
    wild = next(s for _, s, _ in sheets if max(s["chaos"][w] for w in SHORT) >= CHAOTIC)
    assert check_reasons("A frantic, scrappy spell.", wild, CLUBS) == []


def test_negated_reasons_are_left_alone(sheets):
    s = next(s for m, s, _ in sheets if m.minute > 10 and _high(s, "RVA") < 2)
    assert check_reasons("Riverside's press has lost its bite.", s, CLUBS) == []
    assert check_reasons("Riverside are not pressing any more.", s, CLUBS) == []


def test_tiredness_only_late_on(sheets):
    m, s, _ = next(x for x in sheets if x[0].minute < 40)
    assert check_reasons("Kingsport look tired.", s, CLUBS, minute=m.minute)
    m, s, _ = next(x for x in sheets if x[0].minute > 70)
    assert check_reasons("Kingsport look tired.", s, CLUBS, minute=m.minute) == []


def test_template_lines_pass_the_critic(sheets):
    for m, s, names in sheets:
        text = f"{headline_for(m, CLUBS, names)}. {template_line(m, names, CLUBS)}"
        assert check_reasons(text, s, CLUBS, m.type, m.team, m.minute) == [], text
