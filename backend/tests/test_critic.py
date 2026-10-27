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


def sheet(ksc=None, rva=None, chaos=0.4, momentum=0):
    """A hand-made fact sheet: the same metrics in every window unless a dict of overrides says otherwise."""
    base = {"possession_pct": 50, "pass_accuracy_pct": 84, "high_regains": 0, "xg": 0.5, "shots": 4}

    def team(over):
        return {w: {**base, **(over or {})} for w in (*SHORT, None)}

    return {
        "snapshot": {"score": {"KSC": 0, "RVA": 0}, "momentum": momentum},
        "metrics": {"KSC": team(ksc), "RVA": team(rva)},
        "chaos": dict.fromkeys(SHORT, chaos),
    }


# (caption, sheet where it's true, sheet where it isn't). Every reason the Critic knows, both ways.
CASES = [
    ("Kingsport press high.", sheet(ksc={"high_regains": 3}), sheet()),
    (
        "Kingsport are in control.",
        sheet(ksc={"possession_pct": 62}, rva={"possession_pct": 38}),
        sheet(ksc={"possession_pct": 45}, rva={"possession_pct": 55}),
    ),
    ("Kingsport are on top.", sheet(momentum=55), sheet(momentum=-20)),
    (
        "Riverside are losing their grip.",
        sheet(rva={"possession_pct": 44}),
        sheet(rva={"possession_pct": 60, "pass_accuracy_pct": 88}, chaos=0.3),
    ),
    ("It's scrappy and end-to-end.", sheet(chaos=0.7), sheet(chaos=0.3)),
    ("Kingsport look calm on the ball.", sheet(chaos=0.3), sheet(chaos=0.8)),
    (
        "Riverside sit deep.",
        sheet(rva={"possession_pct": 38}),
        sheet(rva={"possession_pct": 55}),
    ),
    (
        "Kingsport's passing is crisp.",
        sheet(ksc={"pass_accuracy_pct": 88}),
        sheet(ksc={"pass_accuracy_pct": 70}),
    ),
    (
        "Riverside's sloppy passing is costing them.",
        sheet(rva={"pass_accuracy_pct": 70}),
        sheet(rva={"pass_accuracy_pct": 90}, chaos=0.3),
    ),
    (
        "Kingsport are creating the better chances.",
        sheet(ksc={"xg": 1.4}, rva={"xg": 0.3}),
        sheet(ksc={"xg": 0.2, "shots": 1}, rva={"xg": 1.1, "shots": 6}),
    ),
    (
        "Riverside scored against the run of play.",
        sheet(rva={"possession_pct": 40}, momentum=30),
        sheet(rva={"possession_pct": 64}, momentum=-40),
    ),
]


@pytest.mark.parametrize(("text", "true", "false"), CASES, ids=[c[0] for c in CASES])
def test_every_reason_is_checked_both_ways(text, true, false):
    assert check_reasons(text, true, CLUBS) == [], text
    problems = check_reasons(text, false, CLUBS)
    assert problems and problems[0].startswith("reason not backed by the data"), text


def test_perfect_passing_needs_every_pass():
    assert check_reasons(
        "Kingsport's passing was perfect.", sheet(ksc={"pass_accuracy_pct": 92}), CLUBS
    )
    assert not check_reasons(
        "Kingsport's passing was perfect.", sheet(ksc={"pass_accuracy_pct": 100}), CLUBS
    )


def test_tiredness_is_a_late_game_reason_only():
    assert check_reasons("Riverside look tired.", sheet(), CLUBS, minute=30)
    assert not check_reasons("Riverside look tired.", sheet(), CLUBS, minute=78)


@pytest.mark.parametrize(
    "text",
    [
        "Kingsport aren't pressing anymore.",
        "There's no press from Riverside.",
        "Riverside's press has lost its bite.",
        "Kingsport could tire later on.",
        "If Riverside press, Kingsport may struggle.",
        "Kingsport tried to reduce the chaos.",
    ],
)
def test_denials_fades_and_maybes_are_not_claims(text):
    assert check_reasons(text, sheet(), CLUBS, minute=20) == [], text


def test_clubs_from_other_matches_are_left_alone():
    assert check_reasons("Ashvale press high at Dunmore.", sheet(), CLUBS) == []


def test_a_pressing_spell_moment_backs_its_own_pressing_line():
    assert not check_reasons(
        "Kingsport press high.", sheet(), CLUBS, moment_type="pressing_spell", moment_team="KSC"
    )


def test_recaps_may_use_the_whole_half():
    s = sheet()
    s["metrics"]["KSC"][None]["high_regains"] = 9
    s["metrics"]["RVA"][None]["high_regains"] = 2
    assert check_reasons(
        "Kingsport pressed well all half.", s, CLUBS
    )  # not a recap: recent windows only
    assert not check_reasons(
        "Kingsport pressed well all half.", s, CLUBS, moment_type="half_time_recap"
    )


def test_each_wrong_reason_is_reported_once():
    text = "Riverside press, Riverside press again, and Riverside keep pressing."
    assert len(check_reasons(text, sheet(), CLUBS)) == 1
