"""Fictional clubs and players.

Surnames are built from invented syllables so no generated player shares a
name with a real footballer by design. Rosters use a fixed seed per club, so
the same players appear in every simulated match.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# 4-3-3 starting shape: role, number, base x, base y.
# x is metres from the team's own goal line, y metres from the right touchline.
STARTING_SHAPE = [
    ("GK", 1, 5, 34),
    ("RB", 2, 30, 60),
    ("CB", 4, 22, 44),
    ("CB", 5, 22, 24),
    ("LB", 3, 30, 8),
    ("DM", 6, 42, 34),
    ("CM", 8, 52, 46),
    ("CM", 10, 52, 22),
    ("RW", 7, 76, 58),
    ("ST", 9, 84, 34),
    ("LW", 11, 76, 10),
]
BENCH_SHAPE = [
    ("GK", 13, 5, 34),
    ("CB", 15, 22, 34),
    ("CM", 14, 52, 34),
    ("RW", 17, 76, 58),
    ("ST", 19, 84, 34),
]

FIRST_NAMES = [
    "Teo",
    "Ari",
    "Malo",
    "Juno",
    "Kasi",
    "Renzo",
    "Ilan",
    "Davo",
    "Oren",
    "Tavi",
    "Lio",
    "Bram",
    "Niko",
    "Sol",
    "Eli",
    "Rafe",
    "Jory",
    "Cas",
    "Dario",
    "Femi",
    "Yann",
    "Oli",
    "Remy",
    "Kian",
    "Zev",
    "Arlo",
    "Tomas",
    "Luca",
    "Idris",
    "Noa",
]
SURNAME_HEADS = [
    "Mar",
    "Vel",
    "Dor",
    "Kas",
    "Bren",
    "Tal",
    "Ost",
    "Fen",
    "Ruv",
    "Hal",
    "Cor",
    "Lun",
    "Ves",
    "Mor",
    "Tren",
    "Gal",
    "Pell",
    "Sar",
    "Wex",
    "Quin",
]
SURNAME_TAILS = [
    "rick",
    "ano",
    "eda",
    "ley",
    "ani",
    "oro",
    "ten",
    "sby",
    "ard",
    "ino",
    "ume",
    "ath",
    "ova",
    "ier",
    "und",
    "ello",
    "ake",
    "ish",
    "orne",
    "avi",
]

# Attribute centre per role: passing, pace, dribbling, finishing, tackling, pressing.
ROLE_PROFILE = {
    "GK": (62, 45, 30, 15, 35, 30),
    "RB": (68, 76, 64, 40, 70, 68),
    "LB": (68, 76, 64, 40, 70, 68),
    "CB": (66, 62, 45, 35, 79, 62),
    "DM": (76, 62, 60, 48, 74, 72),
    "CM": (79, 66, 70, 58, 63, 70),
    "RW": (72, 84, 79, 68, 40, 64),
    "LW": (72, 84, 79, 68, 40, 64),
    "ST": (66, 79, 72, 81, 38, 66),
}


@dataclass(frozen=True)
class TeamStyle:
    possession: float  # 0..1, preference for short, safe passes
    pressing: float  # 0..1, how often they press the ball carrier
    directness: float  # 0..1, how far forward passes travel


@dataclass(frozen=True)
class Player:
    id: str
    name: str
    number: int
    role: str
    base_x: float
    base_y: float
    passing: int
    pace: int
    dribbling: int
    finishing: int
    tackling: int
    pressing: int
    stamina: int


@dataclass
class Club:
    code: str
    name: str
    colors: tuple[str, str]
    style: TeamStyle
    players: list[Player] = field(default_factory=list)

    @property
    def starters(self) -> list[Player]:
        return self.players[:11]

    @property
    def bench(self) -> list[Player]:
        return self.players[11:]

    def player(self, player_id: str) -> Player:
        for p in self.players:
            if p.id == player_id:
                return p
        raise KeyError(player_id)


def _attr(rng: random.Random, centre: int, quality: int) -> int:
    return max(20, min(95, round(rng.gauss(centre + quality, 5))))


def build_club(
    code: str, name: str, colors: tuple[str, str], style: TeamStyle, quality: int, seed: int
) -> Club:
    rng = random.Random(seed)
    used: set[str] = set()
    players = []
    for role, number, bx, by in STARTING_SHAPE + BENCH_SHAPE:
        while True:
            name_ = (
                f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAME_HEADS)}{rng.choice(SURNAME_TAILS)}"
            )
            if name_ not in used:
                used.add(name_)
                break
        pa, pc, dr, fi, ta, pr = ROLE_PROFILE[role]
        players.append(
            Player(
                id=f"{code}-{number:02d}",
                name=name_,
                number=number,
                role=role,
                base_x=bx,
                base_y=by,
                passing=_attr(rng, pa, quality),
                pace=_attr(rng, pc, quality),
                dribbling=_attr(rng, dr, quality),
                finishing=_attr(rng, fi, quality),
                tackling=_attr(rng, ta, quality),
                pressing=_attr(rng, pr, quality),
                stamina=_attr(rng, 74, 0),
            )
        )
    return Club(code, name, colors, style, players)


def kingsport_city() -> Club:
    """A possession side that presses high."""
    return build_club(
        "KSC",
        "Kingsport City",
        ("#1f4e9c", "#f2c230"),
        TeamStyle(possession=0.62, pressing=0.70, directness=0.35),
        quality=2,
        seed=1101,
    )


def riverside_athletic() -> Club:
    """A direct side that sits deeper and plays forward quickly."""
    return build_club(
        "RVA",
        "Riverside Athletic",
        ("#2e7d4f", "#f4f4f4"),
        TeamStyle(possession=0.45, pressing=0.45, directness=0.62),
        quality=0,
        seed=2202,
    )
