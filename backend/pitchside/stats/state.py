"""MatchState: the single source of truth for every number Pitchside shows.

Feed it events in order with ingest(). It keeps running totals, answers
windowed queries, and returns candidate moments with a significance score
and the evidence behind them. Agents never compute numbers themselves; they
ask this object (through the MCP tools) and the Verifier checks against it.
"""

from __future__ import annotations

import itertools
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field

from .metrics import chaos_index, momentum_display, pass_difficulty, threat

ON_BALL = {"pass", "carry", "dribble", "shot", "corner", "clearance"}
REGAIN = {"tackle", "interception"}
MOMENTUM_TAU_S = 180.0


@dataclass
class Evidence:
    metric: str
    value: float | int | str
    team: str | None = None
    player: str | None = None
    window_s: int | None = None


@dataclass
class Moment:
    id: str
    type: str
    t_ms: int
    minute: int
    team: str | None
    player: str | None
    significance: int
    summary: str
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class MatchState:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.meta: dict = {}
        self.teams: list[str] = []
        self.names: dict[str, str] = {}
        self.score: Counter = Counter()
        self.t_ms = 0
        self.minute = 0
        self.period = 1
        self.possession_ms: Counter = Counter()
        self.owner: str | None = None
        self.owner_since = 0
        self.momentum_raw = 0.0
        self.momentum_t = 0
        self.momentum_history: list[tuple[int, int]] = []  # (t_ms, display value)
        self.player = defaultdict(Counter)  # per-player counting stats
        self.physical: dict[str, dict] = {}
        self.moments: list[Moment] = []
        self._cooldown: dict[tuple[str, str | None], int] = {}
        self._chaos_high = False

    # ---------- ingest ----------

    def ingest(self, ev: dict) -> list[Moment]:
        self.events.append(ev)
        self.t_ms, self.period = ev["t_ms"], ev["period"]
        self.minute = ev.get("minute", self.minute)
        kind, team, pid = ev["type"], ev.get("team"), ev.get("player")
        new: list[Moment] = []

        if kind == "match_start":
            self.meta = ev["data"]
            for side in ("home", "away"):
                club = self.meta[side]
                self.teams.append(club["code"])
                for p in club["players"]:
                    self.names[p["id"]] = p["name"]
            return new

        if kind in ON_BALL and team:
            self._own(team)
        self._update_momentum(ev)

        stats = self.player[pid] if pid else None
        if kind == "pass" and stats is not None:
            stats["passes"] += 1
            if ev["outcome"] == "complete":
                stats["passes_complete"] += 1
            if stats["passes"] in (50, 75):
                new += self._moment(
                    "milestone",
                    ev,
                    25 + stats["passes"] // 5,
                    f"{self.name(pid)} reaches {stats['passes']} passes",
                    [Evidence("passes", stats["passes"], team, pid)],
                    key=f"passes{stats['passes']}",
                )
        elif kind == "shot" and stats is not None:
            stats["shots"] += 1
            stats["xg_milli"] += round(ev["xg"] * 1000)
            if ev["outcome"] != "goal" and ev["xg"] >= 0.25:
                new += self._moment(
                    "big_chance",
                    ev,
                    55 + round(ev["xg"] * 40),
                    f"Big chance for {self.name(pid)}",
                    [
                        Evidence("xg", round(ev["xg"], 2), team, pid),
                        Evidence("shot_speed_kmh", ev["shot_speed_kmh"], team, pid),
                        Evidence("outcome", ev["outcome"], team, pid),
                    ],
                    cooldown_s=30,
                )
        elif kind == "goal":
            self.score[team] += 1
            stats["goals"] += 1
            if ev.get("assist_player"):
                self.player[ev["assist_player"]]["assists"] += 1
            shot = next(e for e in reversed(self.events) if e["type"] == "shot")
            new += self._moment(
                "goal",
                ev,
                100,
                f"Goal for {team}: {self.name(pid)}",
                [
                    Evidence("score", self.score_line()),
                    Evidence("xg", round(shot["xg"], 2), team, pid),
                    Evidence("shot_speed_kmh", shot["shot_speed_kmh"], team, pid),
                ],
                cooldown_s=0,
            )
        elif kind in REGAIN and ev.get("outcome", "won") == "won" and stats is not None:
            stats["regains"] += 1
            if ev["x"] >= 52.5:
                stats["high_regains"] += 1
                new += self._check_press(ev)
        elif kind == "card":
            stats["cards"] += 1
            sig = 85 if ev["card"] == "red" else 35
            new += self._moment(
                "card",
                ev,
                sig,
                f"{ev['card'].title()} card for {self.name(pid)}",
                [Evidence("card", ev["card"], team, pid)],
                cooldown_s=0,
            )
        elif kind == "sprint":
            top = max(self.physical.get(pid, {}).get("top_speed_kmh", 0), ev["speed_kmh"])
            self.physical.setdefault(pid, {})["top_speed_kmh"] = top
            if ev["speed_kmh"] >= 34:
                new += self._moment(
                    "player_speed",
                    ev,
                    20,
                    f"{self.name(pid)} hits {ev['speed_kmh']} km/h",
                    [Evidence("speed_kmh", ev["speed_kmh"], team, pid)],
                    cooldown_s=600,
                    key=pid,
                )
        elif kind == "physical":
            for p, v in ev["data"]["players"].items():
                before = self.physical.get(p, {}).get("distance_m", 0)
                self.physical[p] = v
                if before < 10000 <= v["distance_m"]:
                    new += self._moment(
                        "milestone",
                        ev,
                        30,
                        f"{self.name(p)} passes 10 km covered",
                        [Evidence("distance_m", v["distance_m"], self.team_of(p), p)],
                        key=f"10k{p}",
                        player=p,
                        team=self.team_of(p),
                    )

        if kind in ON_BALL | REGAIN | {"possession_change"}:
            new += self._check_swing(ev)
            new += self._check_chaos(ev)
        self.moments += new
        return new

    # ---------- queries (exposed to agents as tools) ----------

    def name(self, pid: str | None) -> str:
        return self.names.get(pid or "", pid or "")

    def team_of(self, pid: str) -> str:
        return pid.split("-")[0]

    def score_line(self) -> str:
        a, b = self.teams
        return f"{a} {self.score[a]}-{self.score[b]} {b}"

    def window(self, seconds: int | None) -> list[dict]:
        if seconds is None:
            return self.events
        start = self.t_ms - seconds * 1000
        return [e for e in self.events if e["t_ms"] >= start]

    def team_metrics(self, team: str, window_s: int | None = None) -> dict:
        evs = self.window(window_s)
        passes = [e for e in evs if e["type"] == "pass" and e["team"] == team]
        done = [e for e in passes if e["outcome"] == "complete"]
        pressed = [e for e in passes if e.get("under_pressure")]
        shots = [e for e in evs if e["type"] == "shot" and e["team"] == team]
        regains = [
            e
            for e in evs
            if e["type"] in REGAIN and e.get("team") == team and e.get("outcome", "won") == "won"
        ]
        span_min = max(1.0, (min(window_s or 10**9, self.t_ms / 1000)) / 60)
        return {
            "team": team,
            "window_s": window_s,
            "possession_pct": self.possession_pct(team, window_s),
            "passes": len(passes),
            "pass_accuracy_pct": round(100 * len(done) / len(passes)) if passes else None,
            "pass_accuracy_under_pressure_pct": (
                round(100 * sum(e["outcome"] == "complete" for e in pressed) / len(pressed))
                if pressed
                else None
            ),
            "avg_pass_difficulty": round(sum(pass_difficulty(e) for e in passes) / len(passes))
            if passes
            else None,
            "shots": len(shots),
            "xg": round(sum(e["xg"] for e in shots), 2),
            "regains": len(regains),
            "high_regains": sum(e["x"] >= 52.5 for e in regains),
            "ppda": self.ppda(team, window_s),
            "tempo_passes_per_min": round(len(passes) / span_min, 1),
        }

    def possession_pct(self, team: str, window_s: int | None = None) -> int:
        if window_s is None:
            owned = Counter(self.possession_ms)
            if self.owner:
                owned[self.owner] += self.t_ms - self.owner_since
        else:
            owned = Counter()
            evs = [e for e in self.window(window_s) if e["type"] in ON_BALL and e.get("team")]
            for a, b in itertools.pairwise(evs):
                owned[a["team"]] += b["t_ms"] - a["t_ms"]
        total = sum(owned.values())
        return round(100 * owned[team] / total) if total else 50

    def ppda(self, team: str, window_s: int | None = 600) -> float | None:
        """Opponent passes in their own 60% per defensive action by `team` there. Lower = more intense press."""
        opp = self.other(team)
        evs = self.window(window_s)
        opp_passes = sum(
            1 for e in evs if e["type"] == "pass" and e["team"] == opp and e["x"] <= 63
        )
        actions = sum(
            1
            for e in evs
            if e.get("team") == team
            and e["type"] in {"tackle", "interception", "foul"}
            and e.get("x", 0) >= 42
            and e.get("outcome") != "missed"
        )
        return round(opp_passes / actions, 1) if actions else None

    def chaos(self, window_s: int = 300) -> float:
        evs = self.window(window_s)
        minutes = max(1.0, min(window_s, self.t_ms / 1000) / 60)
        turnovers = sum(e["type"] == "possession_change" for e in evs)
        duels = sum(e["type"] in {"tackle", "foul", "dribble"} for e in evs)
        on_ball = [e for e in evs if e["type"] in ON_BALL and e.get("team")]
        spells, start = [], None
        for a, b in itertools.pairwise(on_ball):
            start = start if start is not None else a["t_ms"]
            if a["team"] != b["team"]:
                spells.append(b["t_ms"] - start)
                start = None
        avg_s = (sum(spells) / len(spells) / 1000) if spells else 30.0
        return chaos_index(turnovers / minutes, avg_s, duels / minutes)

    def momentum(self) -> int:
        decay = math.exp(-(self.t_ms - self.momentum_t) / 1000 / MOMENTUM_TAU_S)
        return momentum_display(self.momentum_raw * decay)

    def player_summary(self, pid: str) -> dict:
        s = self.player[pid]
        phys = self.physical.get(pid, {})
        return {
            "player": pid,
            "name": self.name(pid),
            "team": self.team_of(pid),
            "passes": s["passes"],
            "pass_accuracy_pct": round(100 * s["passes_complete"] / s["passes"])
            if s["passes"]
            else None,
            "shots": s["shots"],
            "xg": round(s["xg_milli"] / 1000, 2),
            "goals": s["goals"],
            "assists": s["assists"],
            "regains": s["regains"],
            "high_regains": s["high_regains"],
            "distance_m": phys.get("distance_m"),
            "top_speed_kmh": phys.get("top_speed_kmh"),
        }

    def snapshot(self) -> dict:
        """Everything the UI score bug and stat strips need, in one call."""
        a, b = self.teams
        return {
            "t_ms": self.t_ms,
            "minute": self.minute,
            "period": self.period,
            "score": {a: self.score[a], b: self.score[b]},
            "possession_pct": {a: self.possession_pct(a), b: self.possession_pct(b)},
            "momentum": self.momentum(),
            "chaos_5min": self.chaos(300),
            "xg": {t: self.team_metrics(t)["xg"] for t in self.teams},
        }

    def other(self, team: str) -> str:
        a, b = self.teams
        return b if team == a else a

    # ---------- internals ----------

    def _own(self, team: str) -> None:
        if self.owner != team:
            if self.owner:
                self.possession_ms[self.owner] += self.t_ms - self.owner_since
            self.owner, self.owner_since = team, self.t_ms

    def _update_momentum(self, ev: dict) -> None:
        team = ev.get("team")
        if not team or not self.teams:
            return
        value = 0.0
        if (
            ev["type"] in {"pass", "carry", "dribble"}
            and ev.get("outcome", "complete") == "complete"
            and "end_x" in ev
        ):
            value = max(0.0, threat(ev["end_x"], ev["end_y"]) - threat(ev["x"], ev["y"]))
        elif ev["type"] == "shot":
            value = ev["xg"]
        if not value:
            return
        decay = math.exp(-(ev["t_ms"] - self.momentum_t) / 1000 / MOMENTUM_TAU_S)
        sign = 1 if team == self.teams[0] else -1
        self.momentum_raw = self.momentum_raw * decay + sign * value
        self.momentum_t = ev["t_ms"]
        self.momentum_history.append((ev["t_ms"], momentum_display(self.momentum_raw)))

    def _moment(
        self,
        type_: str,
        ev: dict,
        significance: int,
        summary: str,
        evidence: list[Evidence],
        cooldown_s: int = 180,
        key: str | None = None,
        player: str | None = None,
        team: str | None = None,
    ) -> list[Moment]:
        team = team or ev.get("team")
        k = (type_, key or team)
        if cooldown_s and ev["t_ms"] - self._cooldown.get(k, -(10**9)) < cooldown_s * 1000:
            return []
        self._cooldown[k] = ev["t_ms"]
        return [
            Moment(
                id=f"mo-{ev['event_id']}-{type_}",
                type=type_,
                t_ms=ev["t_ms"],
                minute=ev.get("minute", self.minute),
                team=team,
                player=player or ev.get("player"),
                significance=min(100, significance),
                summary=summary,
                evidence=evidence,
            )
        ]

    def _check_press(self, ev: dict) -> list[Moment]:
        team = ev["team"]
        recent = [
            e
            for e in self.window(90)
            if e["type"] in REGAIN
            and e.get("team") == team
            and e.get("outcome", "won") == "won"
            and e["x"] >= 52.5
        ]
        if len(recent) < 3:
            return []
        opp = self.other(team)
        ev_list = [
            Evidence("high_regains", len(recent), team, window_s=90),
            Evidence("ppda", self.ppda(team, 600), team, window_s=600),
        ]
        acc = self.team_metrics(opp, 600)["pass_accuracy_under_pressure_pct"]
        if acc is not None:
            ev_list.append(Evidence("pass_accuracy_under_pressure_pct", acc, opp, window_s=600))
        return self._moment(
            "pressing_spell",
            ev,
            55 + 5 * (len(recent) - 3),
            f"{team} win the ball back {len(recent)} times in 90 seconds in {opp}'s half",
            ev_list,
        )

    def _check_swing(self, ev: dict) -> list[Moment]:
        hist = self.momentum_history
        if len(hist) < 2:
            return []
        now_t, now_v = hist[-1]
        past = [v for t, v in hist if now_t - 180_000 <= t <= now_t - 60_000]
        if not past:
            return []
        delta = now_v - past[0]
        if abs(delta) < 70:
            return []
        team = self.teams[0] if delta > 0 else self.teams[1]
        return self._moment(
            "momentum_swing",
            ev,
            50 + min(20, (abs(delta) - 70) // 3),
            f"Momentum swings towards {team}",
            [
                Evidence("momentum", now_v, window_s=180),
                Evidence("momentum_change", delta, window_s=180),
            ],
            team=team,
            player=None,
            cooldown_s=300,
            key="swing",
        )

    def _check_chaos(self, ev: dict) -> list[Moment]:
        if self.t_ms < 300_000:
            return []
        c = self.chaos(300)
        if not self._chaos_high and c >= 0.68:
            self._chaos_high = True
            return self._moment(
                "chaos_spike",
                ev,
                50,
                "The game has turned chaotic",
                [
                    Evidence("chaos_index", c, window_s=300),
                    Evidence(
                        "turnovers",
                        sum(e["type"] == "possession_change" for e in self.window(300)),
                        window_s=300,
                    ),
                ],
                team=None,
                player=None,
                key="chaos",
            )
        if self._chaos_high and c <= 0.55:
            self._chaos_high = False
        return []
