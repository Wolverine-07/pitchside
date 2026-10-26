"""Pure metric functions. No state, no I/O: easy to test and to explain."""

from __future__ import annotations

import math

PITCH_X = 105.0


def threat(x: float, y: float) -> float:
    """Rough expected-threat value of having the ball at (x, y), 0 to about 0.35."""
    depth = math.exp(-(PITCH_X - x) / 18)
    width = 1 - 0.6 * min(1.0, abs(y - 34) / 34)
    return 0.35 * depth * width


def pass_difficulty(ev: dict) -> int:
    """0 (routine) to 100 (very hard), from length, forwardness, pressure and target zone."""
    length = ev.get("length_m") or math.hypot(ev["end_x"] - ev["x"], ev["end_y"] - ev["y"])
    forward = max(0.0, ev["end_x"] - ev["x"])
    tags = ev.get("tags", [])
    z = (
        -2.6
        + 0.045 * length
        + 0.03 * forward
        + (0.9 if ev.get("under_pressure") else 0)
        + (0.8 if ev["end_x"] > 88 else 0)
        + (0.6 if "line_breaking" in tags else 0)
        + (0.7 if "cross" in tags else 0)
    )
    return round(100 / (1 + math.exp(-z)))


def chaos_index(turnovers_per_min: float, avg_possession_s: float, duels_per_min: float) -> float:
    """Control (0) vs chaos (1): many turnovers, short possessions and lots of duels."""
    t = min(1.0, turnovers_per_min / 4)
    length = min(1.0, avg_possession_s / 30)
    d = min(1.0, duels_per_min / 6)
    return round(0.5 * t + 0.3 * (1 - length) + 0.2 * d, 3)


def momentum_display(raw: float) -> int:
    """Map the raw momentum sum to -100 (away on top) .. +100 (home on top)."""
    return round(100 * math.tanh(raw / 0.6))


def win_probability(
    home_goals: int, away_goals: int, home_xg: float, away_xg: float, minute: float
) -> dict[str, float]:
    """Live home / draw / away probabilities from the score, chance quality so far and time left.

    Each side's scoring rate is a blend of a league-average prior (1.35 goals per 90) and its
    own xG rate in this match, weighted towards the match as it goes on. Remaining goals are
    Poisson; we sum over plausible final scores.
    """
    played = max(minute, 1.0)
    remaining = max(0.0, 93.0 - minute) / 90.0
    weight = min(1.0, played / 60.0)
    prior = 1.35

    def rate(xg: float) -> float:
        return ((1 - weight) * prior + weight * (xg / played * 90.0)) * remaining

    lh, la = rate(home_xg), rate(away_xg)

    def pmf(lam: float, k: int) -> float:
        return math.exp(-lam) * lam**k / math.factorial(k)

    home = draw = away = 0.0
    for i in range(8):
        for j in range(8):
            p = pmf(lh, i) * pmf(la, j)
            h, a = home_goals + i, away_goals + j
            if h > a:
                home += p
            elif h == a:
                draw += p
            else:
                away += p
    total = home + draw + away
    return {
        "home": round(home / total, 3),
        "draw": round(draw / total, 3),
        "away": round(away / total, 3),
    }
