"""Possession-chain match simulator.

Every event depends on where the ball is, who has it, how much pressure they
are under, how tired they are and what the score is. Runs are fully
reproducible from a seed.

Coordinates are metres on a 105 x 68 pitch in the acting team's attacking
direction: x = 0 is their own goal line and x = 105 the goal they attack.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .roster import Club, Player, TeamStyle

PITCH_X, PITCH_Y = 105.0, 68.0
HALF_SECONDS = 45 * 60
ATTACKERS = {"RW", "LW", "ST"}
VENUES = {
    "KSC": "Kingsport Harbour Ground",
    "RVA": "The Riverside Bowl",
    "AVU": "Ashvale Park",
    "BWF": "Brightwater Quay",
    "CHT": "Coldharbour Lane",
    "DMA": "The Dunmore Works",
    "EMW": "Eastmere Common",
    "FHF": "Fairhaven Woodside",
}
WIDE = {"RB", "LB", "RW", "LW"}


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _flip(x: float, y: float) -> tuple[float, float]:
    return PITCH_X - x, PITCH_Y - y


def goal_angle(x: float, y: float) -> float:
    """Angle in radians the goal mouth subtends from (x, y)."""
    dx, dy = PITCH_X - x, abs(y - 34.0)
    half = 7.32 / 2
    a = math.atan2(half - dy, dx) + math.atan2(half + dy, dx)
    return max(0.0, a)


def expected_goals(x: float, y: float, pressed: bool, header: bool) -> float:
    dist = math.hypot(PITCH_X - x, y - 34.0)
    z = (
        -1.6
        - 0.1 * dist
        + 1.6 * goal_angle(x, y)
        - (0.35 if pressed else 0)
        - (0.6 if header else 0)
    )
    return _sigmoid(z)


@dataclass(frozen=True)
class Boost:
    """A scripted nudge so a demo match reliably contains a given story."""

    team: str
    start_min: float
    end_min: float
    pressing: float = 0.0
    directness: float = 0.0
    finishing: float = 1.0


STORYLINES: dict[str, list[Boost]] = {
    "none": [],
    # Riverside score early, Kingsport turn up the press after the hour and come back.
    "comeback": [
        Boost("RVA", 6, 22, finishing=3.0),
        Boost("KSC", 60, 75, pressing=0.30, finishing=2.2),
        Boost("KSC", 75, 95, pressing=0.15, finishing=1.8),
    ],
}


class MatchSim:
    def __init__(
        self,
        home: Club,
        away: Club,
        seed: int,
        storyline: str = "none",
        match_id: str | None = None,
    ) -> None:
        self.rng = random.Random(seed)
        self.seed = seed
        self.home, self.away = home, away
        self.clubs = {home.code: home, away.code: away}
        self.storyline = storyline
        self.boosts = STORYLINES[storyline]
        self.match_id = match_id or f"{home.code.lower()}-{away.code.lower()}-s{seed}"

        self.on_pitch = {c.code: list(c.starters) for c in (home, away)}
        self.bench = {c.code: list(c.bench) for c in (home, away)}
        self.entered = {p.id: 0.0 for c in (home, away) for p in c.starters}
        self.subs_left = {c.code: 3 for c in (home, away)}
        self.sub_minutes = {
            c.code: sorted(self.rng.uniform(58, 82) for _ in range(3)) for c in (home, away)
        }
        self.yellows: set[str] = set()
        self.score = {home.code: 0, away.code: 0}
        self.distance = {p.id: 0.0 for c in (home, away) for p in c.players}
        self.top_speed = {p.id: 0.0 for c in (home, away) for p in c.players}

        self.events: list[dict] = []
        self.event_id = 0
        self.period = 1
        self.t = 0.0  # seconds since the current period kicked off
        self.offset = 0.0  # elapsed seconds before this period started
        self.poss = home.code
        self.carrier: Player = home.starters[0]
        self.bx, self.by = 52.5, 34.0
        self.last_pass: dict | None = None

    # ---------- clock and helpers ----------

    @property
    def elapsed(self) -> float:
        return self.offset + self.t

    @property
    def minute(self) -> float:
        return (self.period - 1) * 45 + min(self.t, HALF_SECONDS) / 60

    def other(self, code: str) -> str:
        return self.away.code if code == self.home.code else self.home.code

    def style(self, code: str) -> TeamStyle:
        base = self.clubs[code].style
        press, direct = base.pressing, base.directness
        for b in self.boosts:
            if b.team == code and b.start_min <= self.minute < b.end_min:
                press += b.pressing
                direct += b.directness
        # A side chasing the game after the hour presses higher and goes longer.
        if self.minute >= 60 and self.score[code] < self.score[self.other(code)]:
            press += 0.15
            direct += 0.12
        return TeamStyle(base.possession, _clip(press, 0, 1), _clip(direct, 0, 1))

    def finishing_boost(self, code: str) -> float:
        mult = 1.0
        for b in self.boosts:
            if b.team == code and b.start_min <= self.minute < b.end_min:
                mult *= b.finishing
        return mult

    def fatigue(self, p: Player) -> float:
        on = self.minute - self.entered.get(p.id, 0.0)
        return max(0.0, (on - 55) / 35) * (1.1 - p.stamina / 100) * 0.6

    def pos(self, p: Player, code: str) -> tuple[float, float]:
        """Approximate position of a player, shifted with the ball, in their team's frame."""
        bx, by = (self.bx, self.by) if code == self.poss else _flip(self.bx, self.by)
        shift = 0.1 if p.role == "GK" else 0.55
        return (
            _clip(p.base_x + (bx - 52.5) * shift, 2, 91),
            _clip(p.base_y + (by - 34) * 0.25, 2, 66),
        )

    def nearest(self, code: str, x: float, y: float) -> Player:
        return min(
            self.on_pitch[code],
            key=lambda p: (self.pos(p, code)[0] - x) ** 2 + (self.pos(p, code)[1] - y) ** 2,
        )

    def emit(self, type_: str, team: str | None = None, player: Player | None = None, **kw) -> dict:
        self.event_id += 1
        ev: dict = {
            "match_id": self.match_id,
            "event_id": self.event_id,
            "t_ms": int(self.elapsed * 1000),
            "period": self.period,
            "minute": int(min(self.t, HALF_SECONDS - 1) // 60) + 1 + (self.period - 1) * 45,
            "type": type_,
        }
        if self.t >= HALF_SECONDS:
            ev["added"] = int((self.t - HALF_SECONDS) // 60) + 1
        if team:
            ev["team"] = team
        if player:
            ev["player"] = player.id
        for k, v in kw.items():
            if v is None:
                continue
            ev[k] = round(v, 1) if isinstance(v, float) else v
        self.events.append(ev)
        return ev

    def advance(self, dt: float) -> None:
        """Move the clock and accumulate distance covered by everyone on the pitch."""
        self.t += dt
        for code, players in self.on_pitch.items():
            pressing = self.style(code).pressing
            for p in players:
                rate = (
                    0.9 if p.role == "GK" else 1.7 + 0.3 * pressing + 0.2 * (p.role in {"CM", "DM"})
                )
                self.distance[p.id] += (
                    dt * rate * (1 - 0.3 * self.fatigue(p)) * self.rng.uniform(0.9, 1.1)
                )
                if p.role != "GK" and self.rng.random() < 0.006 * min(dt, 5):
                    self.sprint(code, p)

    def sprint(self, code: str, p: Player) -> None:
        speed = 22 + p.pace * 0.12 - 4 * self.fatigue(p) + self.rng.gauss(0, 1.5)
        self.top_speed[p.id] = max(self.top_speed[p.id], speed)
        if speed >= 33:
            x, y = self.pos(p, code)
            self.emit("sprint", code, p, x=x, y=y, speed_kmh=speed)

    # ---------- match flow ----------

    def run(self) -> list[dict]:
        self.emit("match_start", data=self.meta())
        for period in (1, 2):
            self.period, self.t = period, 0.0
            stoppage = self.rng.uniform(1, 4) * 60 if period == 1 else self.rng.uniform(2, 6) * 60
            self.emit(
                "period_start", data={"kickoff": self.home.code if period == 1 else self.away.code}
            )
            self.kickoff(self.home.code if period == 1 else self.away.code)
            next_snapshot = 300.0
            while self.t < HALF_SECONDS + stoppage:
                self.maybe_substitute()
                self.step()
                if self.t >= next_snapshot:
                    self.snapshot()
                    next_snapshot += 300.0
            self.emit("period_end", data={"score": dict(self.score)})
            self.snapshot()
            if period == 2:
                self.emit("match_end", data={"score": dict(self.score)})
            self.offset += self.t
        return self.events

    def meta(self) -> dict:
        def club(c: Club) -> dict:
            return {
                "code": c.code,
                "name": c.name,
                "colors": list(c.colors),
                "players": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "number": p.number,
                        "role": p.role,
                        "starter": i < 11,
                    }
                    for i, p in enumerate(c.players)
                ],
            }

        return {
            "home": club(self.home),
            "away": club(self.away),
            "venue": VENUES.get(self.home.code, f"{self.home.name} Stadium"),
            "seed": self.seed,
            "storyline": self.storyline,
            "pitch": {"length_m": PITCH_X, "width_m": PITCH_Y},
            "synthetic": True,
        }

    def kickoff(self, code: str) -> None:
        self.poss = code
        self.carrier = next(p for p in self.on_pitch[code] if p.role in {"CM", "DM", "ST"})
        self.bx, self.by = 52.5, 34.0
        self.last_pass = None

    def snapshot(self) -> None:
        players = {
            p.id: {
                "distance_m": round(self.distance[p.id]),
                "top_speed_kmh": round(self.top_speed[p.id], 1),
            }
            for code in self.on_pitch
            for p in self.on_pitch[code]
        }
        self.emit("physical", data={"players": players})

    def maybe_substitute(self) -> None:
        for code in (self.home.code, self.away.code):
            mins = self.sub_minutes[code]
            if not mins or self.minute < mins[0] or self.period != 2:
                continue
            mins.pop(0)
            if not self.subs_left[code] or not self.bench[code]:
                continue
            outfield = [p for p in self.on_pitch[code] if p.role != "GK" and p is not self.carrier]
            off = max(outfield, key=self.fatigue)
            same = [b for b in self.bench[code] if b.role == off.role]
            on = same[0] if same else next((b for b in self.bench[code] if b.role != "GK"), None)
            if on is None:
                continue
            self.on_pitch[code][self.on_pitch[code].index(off)] = on
            self.bench[code].remove(on)
            self.entered[on.id] = self.minute
            self.subs_left[code] -= 1
            self.emit("substitution", code, off, player_on=on.id)

    def turnover(
        self, code: str, player: Player, x: float, y: float, how: str, dead: float = 0.0
    ) -> None:
        self.poss, self.carrier = code, player
        self.bx, self.by = _clip(x, 0.5, 104.5), _clip(y, 0.5, 67.5)
        self.last_pass = None
        self.emit("possession_change", code, player, x=self.bx, y=self.by, how=how)
        if dead:
            self.advance(dead)

    # ---------- one action by the ball carrier ----------

    def step(self) -> None:
        opp = self.other(self.poss)
        c = self.carrier
        ostyle = self.style(opp)
        pressed = False

        p_press = (
            0.08
            + 0.30 * ostyle.pressing * (1.0 if self.bx < 52.5 else 0.55)
            + (0.15 if self.bx > 78 else 0)
        )
        if c.role != "GK" and self.rng.random() < p_press:
            ox, oy = _flip(self.bx, self.by)
            presser = self.nearest(opp, ox, oy)
            pressed = True
            self.emit("pressure", opp, presser, x=ox, y=oy, on_player=c.id)
            self.advance(self.rng.uniform(0.3, 1.0))
            if self.rng.random() < 0.24 and self.duel(presser, c):
                return

        in_corner = self.bx > 99 and (self.by < 4 or self.by > 64)
        weights = {"pass": 1.0, "carry": 0.0, "dribble": 0.0, "shot": 0.0}
        if c.role != "GK" and not in_corner:
            weights["carry"] = max(
                0.03, 0.16 + 0.1 * (c.pace - 60) / 40 + (-0.06 if pressed else 0.06)
            )
            weights["dribble"] = (
                0.03 + (0.07 if c.role in ATTACKERS else 0) + (0.04 if pressed else 0)
            )
            if self.bx > 80 and abs(self.by - 34) < 22:
                weights["shot"] = 0.04 + 0.55 * ((self.bx - 80) / 25) ** 1.5 * (
                    1 - abs(self.by - 34) / 22
                )
        action = self.rng.choices(list(weights), weights=list(weights.values()))[0]
        getattr(self, f"do_{action}")(pressed)

    def duel(self, defender: Player, carrier: Player) -> bool:
        """Defender tries to win the ball. Returns True if play stopped or possession changed."""
        opp = self.other(self.poss)
        z = (
            (defender.tackling - carrier.dribbling) / 12
            - 0.2
            + 2 * self.fatigue(carrier)
            - 2 * self.fatigue(defender)
        )
        ox, oy = _flip(self.bx, self.by)
        if self.rng.random() < _sigmoid(z):
            if self.rng.random() < 0.2:
                self.foul(defender, carrier)
                return True
            self.emit("tackle", opp, defender, x=ox, y=oy, outcome="won", on_player=carrier.id)
            self.turnover(opp, defender, ox, oy, how="tackle")
            return True
        self.emit("tackle", opp, defender, x=ox, y=oy, outcome="missed", on_player=carrier.id)
        if self.rng.random() < 0.1:
            self.foul(defender, carrier)
            return True
        return False

    def foul(self, defender: Player, carrier: Player) -> None:
        opp = self.other(self.poss)
        ox, oy = _flip(self.bx, self.by)
        self.emit("foul", opp, defender, x=ox, y=oy, on_player=carrier.id)
        if self.rng.random() < 0.17:
            if defender.id in self.yellows:
                self.emit("card", opp, defender, card="red", reason="second yellow")
                self.on_pitch[opp].remove(defender)
            else:
                self.yellows.add(defender.id)
                self.emit("card", opp, defender, card="yellow")
        self.last_pass = None
        self.advance(self.rng.uniform(12, 30))  # free kick, ball stays with the fouled side

    def do_carry(self, pressed: bool) -> None:
        c = self.carrier
        dist = self.rng.uniform(3, 11) * (0.8 if pressed else 1.25)
        dx = dist * self.rng.uniform(0.55, 1.0)
        dy = math.copysign(math.sqrt(max(0.0, dist**2 - dx**2)), self.rng.uniform(-1, 1))
        speed = _clip(
            13
            + (c.pace - 50) * 0.3
            + (6 if dist > 9 else 0)
            - 5 * self.fatigue(c)
            + self.rng.gauss(0, 2.5),
            9,
            36,
        )
        ex, ey = _clip(self.bx + dx, 1, 103), _clip(self.by + dy, 1, 67)
        self.top_speed[c.id] = max(self.top_speed[c.id], speed)
        self.emit(
            "carry",
            self.poss,
            c,
            x=self.bx,
            y=self.by,
            end_x=ex,
            end_y=ey,
            speed_kmh=speed,
            under_pressure=pressed,
        )
        self.distance[c.id] += dist
        self.bx, self.by = ex, ey
        self.advance(dist / (speed / 3.6) + 0.3)

    def do_dribble(self, pressed: bool) -> None:
        code, opp = self.poss, self.other(self.poss)
        c = self.carrier
        ox, oy = _flip(self.bx, self.by)
        defender = self.nearest(opp, ox, oy)
        z = (c.dribbling - defender.tackling) / 12 + 0.1 - 2 * self.fatigue(c)
        if self.rng.random() < _sigmoid(z):
            gain = self.rng.uniform(4, 9)
            ex, ey = _clip(self.bx + gain, 1, 103), _clip(self.by + self.rng.uniform(-4, 4), 1, 67)
            self.emit(
                "dribble",
                code,
                c,
                x=self.bx,
                y=self.by,
                end_x=ex,
                end_y=ey,
                outcome="complete",
                past_player=defender.id,
                under_pressure=pressed,
            )
            self.bx, self.by = ex, ey
            self.advance(self.rng.uniform(1.5, 3.0))
            return
        self.emit(
            "dribble",
            code,
            c,
            x=self.bx,
            y=self.by,
            outcome="failed",
            past_player=defender.id,
            under_pressure=pressed,
        )
        if self.rng.random() < 0.25:
            self.foul(defender, c)
            return
        self.emit("tackle", opp, defender, x=ox, y=oy, outcome="won", on_player=c.id)
        self.advance(self.rng.uniform(0.5, 1.5))
        self.turnover(opp, defender, ox, oy, how="tackle")

    def do_pass(self, pressed: bool) -> None:
        code, opp = self.poss, self.other(self.poss)
        c = self.carrier
        style = self.style(code)
        skill = c.passing - 25 * self.fatigue(c)
        wide_final_third = self.bx > 80 and (self.by < 15 or self.by > 53)
        in_corner = self.bx > 99 and (self.by < 4 or self.by > 64)
        mates = [p for p in self.on_pitch[code] if p is not c]
        kind = "pass"
        tags: list[str] = []

        if in_corner or (wide_final_third and self.rng.random() < 0.35):
            target = self.rng.choice([p for p in mates if p.role in {"ST", "CB", "RW", "LW", "CM"}])
            px, py = self.rng.uniform(92, 101), self.rng.uniform(26, 42)
            z = -0.35 + (skill - 70) / 15 - (0.4 if pressed else 0)
            tags.append("cross")
        elif pressed and self.bx < 25 and c.role in {"GK", "CB"} and self.rng.random() < 0.4:
            target = self.rng.choice([p for p in mates if p.role in ATTACKERS | {"CM"}])
            px, py = self.rng.uniform(55, 78), self.rng.uniform(10, 58)
            z = -0.2
            kind = "clearance"
        elif self.bx < 60 and self.rng.random() < 0.03 + 0.08 * style.directness:
            target = self.rng.choice([p for p in mates if p.role in ATTACKERS])
            px, py = self.rng.uniform(68, 95), self.rng.uniform(8, 60)
            d = math.hypot(px - self.bx, py - self.by)
            z = 1.6 + (skill - 70) / 12 - 0.035 * d - (0.6 if pressed else 0)
            tags.append("long")
        else:
            options = []
            for p in mates:
                x, y = self.pos(p, code)
                x = _clip(
                    x + self.rng.gauss(0, 4) + (6 * style.directness if p.role in ATTACKERS else 0),
                    2,
                    103,
                )
                y = _clip(y + self.rng.gauss(0, 4), 2, 66)
                d = math.hypot(x - self.bx, y - self.by)
                if d < 5 or (p.role == "GK" and self.bx > 40):
                    continue
                forward = max(0.0, x - self.bx)
                w = math.exp(-d / (16 + 22 * style.directness)) * (
                    1 + forward / 25 * (0.5 + style.directness)
                )
                w *= 0.25 if p.role == "GK" else 1.0
                options.append((w, p, x, y))
            if not options:
                self.do_carry(pressed)
                return
            _, target, px, py = self.rng.choices(options, weights=[o[0] for o in options])[0]
            d = math.hypot(px - self.bx, py - self.by)
            z = (
                3.4
                + (skill - 70) / 12
                - 0.045 * d
                - (0.85 if pressed else 0)
                - 0.012 * max(0, px - self.bx)
                - (0.7 if px > 88 else 0)
            )

        d = math.hypot(px - self.bx, py - self.by)
        dx = px - self.bx
        if dx > 10 and px > 40:
            tags.append("progressive")
        if dx > 18:
            tags.append("line_breaking")
        if d > 30 and "long" not in tags:
            tags.append("long")
        ball_speed = _clip(9 + d * 0.35 + self.rng.uniform(0, 4), 8, 32)
        flight = d / ball_speed
        ok = self.rng.random() < _sigmoid(z)

        ev = self.emit(
            kind,
            code,
            c,
            x=self.bx,
            y=self.by,
            end_x=px,
            end_y=py,
            receiver=target.id if ok else None,
            outcome="complete" if ok else "incomplete",
            under_pressure=pressed,
            ball_speed_kmh=ball_speed * 3.6,
            length_m=d,
            tags=tags or None,
        )
        self.advance(flight)
        if ok:
            self.carrier, self.bx, self.by = target, _clip(px, 1, 104), _clip(py, 1, 67)
            self.last_pass = ev
            self.advance(self.rng.uniform(0.6, 2.0))
            return

        if "cross" in tags and self.rng.random() < 0.3:
            self.corner(code, self.by)
            return
        ox, oy = _flip(px, py)
        if self.rng.random() < 0.35:
            # Out of play: throw-in or goal kick to the other side.
            if px > 100:
                gk = next(
                    (p for p in self.on_pitch[opp] if p.role == "GK"), self.nearest(opp, 6, 34)
                )
                self.turnover(opp, gk, 6, 34, how="goal_kick", dead=self.rng.uniform(15, 28))
            else:
                taker = self.nearest(opp, ox, 1 if oy < 34 else 67)
                self.turnover(
                    opp,
                    taker,
                    ox,
                    1 if oy < 34 else 67,
                    how="throw_in",
                    dead=self.rng.uniform(8, 16),
                )
            return
        interceptor = self.nearest(opp, ox, oy)
        self.emit("interception", opp, interceptor, x=ox, y=oy, from_player=c.id)
        self.turnover(opp, interceptor, ox, oy, how="interception")

    def corner(self, code: str, from_y: float) -> None:
        side = 0.5 if from_y < 34 else 67.5
        taker = next((p for p in self.on_pitch[code] if p.role in {"RW", "LW", "CM"}), self.carrier)
        self.emit("corner", code, taker, x=104.5, y=side)
        self.carrier, self.bx, self.by = taker, 104.5, side
        self.last_pass = None
        self.advance(self.rng.uniform(20, 35))

    def do_shot(self, pressed: bool) -> None:
        code, opp = self.poss, self.other(self.poss)
        c = self.carrier
        header = bool(
            self.last_pass and "cross" in self.last_pass.get("tags", []) and self.rng.random() < 0.6
        )
        xg = expected_goals(self.bx, self.by, pressed, header)
        mult = (0.75 + (c.finishing - 50) / 100) * self.finishing_boost(code)
        p_goal = min(0.95, xg * mult)
        r = self.rng.random()
        if r < p_goal:
            outcome = "goal"
        else:
            rest = (r - p_goal) / (1 - p_goal)
            outcome = "saved" if rest < 0.36 else "blocked" if rest < 0.58 else "off_target"
        dist = math.hypot(PITCH_X - self.bx, self.by - 34)
        speed = _clip(
            58 + c.finishing * 0.45 - dist * 0.25 - (25 if header else 0) + self.rng.gauss(0, 8),
            35,
            130,
        )
        assist = (
            self.last_pass if self.last_pass and self.last_pass.get("receiver") == c.id else None
        )
        if assist:
            assist.setdefault("tags", []).append("key_pass")
        self.emit(
            "shot",
            code,
            c,
            x=self.bx,
            y=self.by,
            end_x=PITCH_X,
            end_y=_clip(34 + self.rng.gauss(0, 3), 28, 40),
            outcome=outcome,
            xg=round(xg, 3),
            shot_speed_kmh=speed,
            body_part="head" if header else "foot",
            under_pressure=pressed,
            assist_player=assist["player"] if assist else None,
        )
        self.advance(self.rng.uniform(0.8, 1.6))

        if outcome == "goal":
            self.score[code] += 1
            self.emit(
                "goal",
                code,
                c,
                assist_player=assist["player"] if assist else None,
                score=dict(self.score),
            )
            self.advance(self.rng.uniform(50, 80))
            self.kickoff(opp)
            return
        corner = (outcome == "saved" and self.rng.random() < 0.28) or (
            outcome == "blocked" and self.rng.random() < 0.45
        )
        if corner:
            self.corner(code, self.by)
            return
        gk = next((p for p in self.on_pitch[opp] if p.role == "GK"), self.nearest(opp, 6, 34))
        if outcome == "saved":
            self.turnover(opp, gk, 8, 34, how="save", dead=self.rng.uniform(4, 10))
        elif outcome == "off_target":
            self.turnover(opp, gk, 6, 34, how="goal_kick", dead=self.rng.uniform(15, 30))
        else:
            ox, oy = _flip(self.bx, self.by)
            self.turnover(opp, self.nearest(opp, ox, oy), ox + 3, oy, how="block")


def simulate(seed: int, storyline: str = "none") -> list[dict]:
    from .roster import kingsport_city, riverside_athletic

    return MatchSim(kingsport_city(), riverside_athletic(), seed=seed, storyline=storyline).run()
