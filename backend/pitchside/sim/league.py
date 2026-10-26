"""The Coastal League: eight fictional clubs, a table going into matchday 10, and live standings.

Every club, player and score is invented. The featured match is Kingsport City v
Riverside Athletic; three other fixtures kick off at the same time, so the table
moves while you watch.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .engine import MatchSim
from .roster import Club, TeamStyle, build_club, kingsport_city, riverside_athletic

LEAGUE_NAME = "The Coastal League"
MATCHDAY = 10

# code, name, colours, style (possession, pressing, directness), quality, roster seed
OTHER_CLUBS = [
    ("AVU", "Ashvale United", ("#b3262e", "#ffffff"), (0.58, 0.62, 0.40), 3, 3303),
    ("BWF", "Brightwater FC", ("#0f8a8a", "#f5d76e"), (0.50, 0.50, 0.55), 1, 4404),
    ("CHT", "Coldharbour Town", ("#5b3c88", "#e8e8e8"), (0.42, 0.40, 0.65), -1, 5505),
    ("DMA", "Dunmore Albion", ("#d9822b", "#1b1b1b"), (0.55, 0.58, 0.45), 2, 6606),
    ("EMW", "Eastmere Wanderers", ("#2f5d9e", "#9fd3ff"), (0.47, 0.45, 0.58), 0, 7707),
    ("FHF", "Fairhaven Forest", ("#24653a", "#d4b04a"), (0.52, 0.66, 0.50), 1, 8808),
]

# Going into matchday 10: played, won, drawn, lost, goals for, goals against.
TABLE_BEFORE = {
    "AVU": (9, 6, 2, 1, 17, 8),
    "KSC": (9, 5, 2, 2, 15, 10),
    "DMA": (9, 5, 1, 3, 14, 11),
    "RVA": (9, 4, 3, 2, 13, 10),
    "FHF": (9, 4, 2, 3, 12, 12),
    "BWF": (9, 3, 3, 3, 11, 12),
    "EMW": (9, 2, 2, 5, 9, 15),
    "CHT": (9, 1, 1, 7, 6, 19),
}

FIXTURES = [("KSC", "RVA"), ("AVU", "DMA"), ("BWF", "CHT"), ("FHF", "EMW")]


def clubs() -> dict[str, Club]:
    out = {"KSC": kingsport_city(), "RVA": riverside_athletic()}
    for code, name, colors, (pos, press, direct), quality, seed in OTHER_CLUBS:
        out[code] = build_club(code, name, colors, TeamStyle(pos, press, direct), quality, seed)
    return out


@dataclass
class Fixture:
    home: str
    away: str
    events: list[dict]
    score: dict[str, int] = field(default_factory=dict)
    minute: int = 0
    finished: bool = False

    @property
    def id(self) -> str:
        return f"{self.home}-{self.away}"


def matchday(seed: int, storyline: str = "none") -> list[Fixture]:
    """All four fixtures, simulated. The featured one uses the given seed and storyline."""
    all_clubs = clubs()
    rng = random.Random(seed * 7919)
    out = []
    for i, (h, a) in enumerate(FIXTURES):
        s = seed if i == 0 else rng.randrange(1, 10_000)
        story = storyline if i == 0 else "none"
        sim = MatchSim(
            all_clubs[h],
            all_clubs[a],
            seed=s,
            storyline=story,
            match_id=f"{h.lower()}-{a.lower()}-s{s}",
        )
        out.append(Fixture(h, a, sim.run(), {h: 0, a: 0}))
    return out


class LeagueState:
    """Live table: the table before the matchday plus the current scores."""

    def __init__(
        self, fixtures: list[Fixture], names: dict[str, str], colors: dict[str, str]
    ) -> None:
        self.fixtures = {f.id: f for f in fixtures}
        self.names = names
        self.colors = colors
        self.before = self.table(live=False)

    def apply(self, fixture_id: str, ev: dict) -> bool:
        """Update a fixture from one of its events. True when the score changed."""
        f = self.fixtures[fixture_id]
        f.minute = ev.get("minute", f.minute)
        if ev["type"] == "goal":
            f.score[ev["team"]] += 1
            return True
        if ev["type"] == "match_end":
            f.finished = True
        return False

    def table(self, live: bool = True) -> list[dict]:
        rows = {code: list(v) for code, v in TABLE_BEFORE.items()}
        if live:
            for f in self.fixtures.values():
                if f.minute == 0:
                    continue
                hg, ag = f.score[f.home], f.score[f.away]
                for code, gf, ga in ((f.home, hg, ag), (f.away, ag, hg)):
                    r = rows[code]
                    r[0] += 1
                    r[1] += gf > ga
                    r[2] += gf == ga
                    r[3] += gf < ga
                    r[4] += gf
                    r[5] += ga
        ranked = sorted(
            rows.items(),
            key=lambda kv: (-(3 * kv[1][1] + kv[1][2]), -(kv[1][4] - kv[1][5]), -kv[1][4], kv[0]),
        )
        return [
            {
                "pos": i + 1,
                "code": code,
                "name": self.names[code],
                "color": self.colors[code],
                "played": r[0],
                "won": r[1],
                "drawn": r[2],
                "lost": r[3],
                "gf": r[4],
                "ga": r[5],
                "gd": r[4] - r[5],
                "points": 3 * r[1] + r[2],
            }
            for i, (code, r) in enumerate(ranked)
        ]

    def position(self, code: str, live: bool = True) -> int:
        return next(r["pos"] for r in self.table(live) if r["code"] == code)

    def scores(self) -> list[dict]:
        return [
            {
                "id": f.id,
                "home": f.home,
                "away": f.away,
                "home_goals": f.score[f.home],
                "away_goals": f.score[f.away],
                "minute": f.minute,
                "finished": f.finished,
            }
            for f in self.fixtures.values()
        ]

    def snapshot(self) -> dict:
        table = self.table()
        before = {r["code"]: r["pos"] for r in self.before}
        for r in table:
            r["moved"] = before[r["code"]] - r["pos"]  # positive = up
        return {
            "league": LEAGUE_NAME,
            "matchday": MATCHDAY,
            "table": table,
            "scores": self.scores(),
        }
