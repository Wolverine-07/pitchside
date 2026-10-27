"""Template lines built only from verified numbers.

Used when the model is unavailable, too slow, or fails the Verifier twice.
They are plain on purpose: correct and on time beats clever and wrong.
"""

from __future__ import annotations

from pitchside.stats.state import Moment


def _ev(m: Moment, metric: str):
    return next((e.value for e in m.evidence if e.metric == metric), None)


def _ordinal(n) -> str:
    n = int(n)
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def template_line(m: Moment, names: dict[str, str], clubs: dict[str, str]) -> str:
    who = names.get(m.player or "", "")
    team = clubs.get(m.team or "", m.team or "")
    match m.type:
        case "goal":
            setter = next((e.player for e in m.evidence if e.metric == "set_up_by"), None)
            assist = f", set up by {names.get(setter, '')}" if setter else ""
            return f"Goal for {team}. {who} scores{assist}, and it's {_ev(m, 'score')}."
        case "big_chance":
            outcome = {"saved": "saved", "blocked": "blocked", "off_target": "off target"}.get(
                str(_ev(m, "outcome")), "missed"
            )
            return f"Big chance for {who}, a chance worth {_ev(m, 'xg')} expected goals, and it's {outcome}."
        case "pressing_spell":
            return f"{team} win the ball back {_ev(m, 'high_regains')} times in 90 seconds in the opposition half."
        case "momentum_swing":
            return f"The momentum is with {team} now."
        case "chaos_spike":
            return f"Scrappy spell: {_ev(m, 'turnovers')} turnovers in the last five minutes."
        case "card":
            return f"{str(_ev(m, 'card')).title()} card for {who}."
        case "player_speed":
            return f"{who} clocked at {_ev(m, 'speed_kmh')} km/h."
        case "half_time_recap" | "full_time_recap":
            when = "Half-time" if m.type == "half_time_recap" else "Full-time"
            scorers = [
                names.get(e.player or "", "") for e in m.evidence if e.metric == "goal_minute"
            ]
            goals = f"Goals from {', '.join(scorers)}." if scorers else "No goals yet."
            return f"{when}, and it's {_ev(m, 'score')}. {goals}"
        case "player_spotlight":
            top = m.evidence[0]
            label = top.metric.replace("_", " ").replace(
                "line breaking or key passes", "line-breaking or key passes"
            )
            return f"{who} has been everywhere: {top.value} {label} in the last ten minutes."
        case "great_save":
            return f"Great save from {who}, keeping out a chance worth {_ev(m, 'xg_saved')} expected goals."
        case "around_the_league":
            pos = _ev(m, "live_position")
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(pos if pos in (1, 2, 3) else 0, "th")
            return f"{m.summary}. {team} are {pos}{suffix} on the live table."
        case "match_preview":
            venue = _ev(m, "venue")
            codes = [e.team for e in m.evidence if e.metric == "live_position"]
            if len(codes) != 2:
                return f"Kick-off at {venue}." if venue else "Kick-off."
            home, away = codes

            def where(code: str) -> str:
                pos = next(
                    e.value for e in m.evidence if e.metric == "live_position" and e.team == code
                )
                pts = next(e.value for e in m.evidence if e.metric == "points" and e.team == code)
                return f"{clubs.get(code, code)} ({_ordinal(pos)}, {pts} points)"

            return (
                f"Kick-off at {venue}: {where(home)} take on {where(away)}. "
                "Three other league games start at the same time."
            )
        case "match_pulse":
            leader = next(e for e in m.evidence if e.metric == "possession_pct")
            shots = {e.team: e.value for e in m.evidence if e.metric == "shots"}
            other = next((t for t in shots if t != leader.team), None)
            ball = (
                f"It's {_ev(m, 'score')}, and {clubs.get(leader.team, leader.team)} have had "
                f"{leader.value}% of the ball {'in the last five minutes' if leader.window_s else 'so far'}"
            )
            if not any(shots.values()):
                return f"{ball}, but neither side has had a shot."
            return f"{ball}, with {shots.get(leader.team, 0)} shots to {shots.get(other, 0)}."
        case "milestone":
            return m.summary + "."
        case _:
            return m.summary + "."
