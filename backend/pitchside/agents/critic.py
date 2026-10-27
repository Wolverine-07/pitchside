"""The Critic: checks the reasons a caption gives, not just its numbers.

A caption can get every number right and still say something the match doesn't show, like
"Riverside press high" when they haven't won the ball in Kingsport's half for five minutes.
The Critic finds each reason a line gives (pressing, control, chaos, calm, sitting deep,
tiredness, passing quality, creating chances), works out which club it is about, and tests it
against the stats engine. Plain code, like the Verifier: a model can't talk its way past it.

The tests are deliberately generous (any recent window will do) so they only catch reasons the
numbers clearly don't support.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from pitchside.agents.verify import CLUB_CODES

SHORT = (90, 180, 300, 600)  # "right now" windows, in seconds
# The broadcast view calls 0.4 to 0.65 "contested"; in that band both "scrappy" and "settled" can be fair.
CHAOTIC = 0.55
SETTLED = 0.6

NEGATION = re.compile(
    r"\b(no|not|never|without|lost|lose|loses|losing|can't|cannot|stopped|drops?|fades?|"
    r"isn't|aren't|hasn't|haven't|little|less|reduc\w*|low|lower\w*|decreas\w*|calm\w*|"
    # Speculation is not a claim about the match: "could tire later", "may fatigue players".
    r"may|might|could|would|possibly|potentially|risk\w*|if)\b[^.]{0,25}$",
    re.IGNORECASE,
)
FADING = re.compile(
    r"^[^.,;]{0,20}\b(lost|losing|gone|fad\w*|dropp\w*|wan\w*|easing|eased)\b", re.IGNORECASE
)


@dataclass
class Reason:
    name: str
    pattern: re.Pattern
    test: Callable[[str | None, dict, dict], tuple[bool, str]]
    team_needed: bool = True


def _m(sheet: dict, team: str, w) -> dict:
    return (sheet.get("metrics") or {}).get(team, {}).get(w) or {}


def _other(sheet: dict, team: str) -> str | None:
    return next((t for t in (sheet.get("metrics") or {}) if t != team), None)


def _windows(ctx: dict) -> tuple:
    """Recaps talk about the whole half, so the whole match counts as evidence too."""
    return (*SHORT, None) if ctx.get("recap") else SHORT


def _momentum_for(sheet: dict, team: str) -> int:
    snap = sheet.get("snapshot") or {}
    home = next(iter(snap.get("score") or {}), None)
    m = snap.get("momentum") or 0
    return m if team == home else -m


def _pressing(team, sheet, ctx):
    if ctx.get("type") == "pressing_spell" and ctx.get("team") == team:
        return True, ""
    best = max((_m(sheet, team, w).get("high_regains") or 0) for w in SHORT)
    if best >= 2:
        return True, ""
    if ctx.get("recap"):
        mine = _m(sheet, team, None).get("high_regains") or 0
        theirs = _m(sheet, _other(sheet, team), None).get("high_regains") or 0
        if mine > theirs:
            return True, ""
    return (
        False,
        f"{ctx['club'](team)} have won the ball back in the opposition half {best} time(s) at most in any recent window",
    )


def _control(team, sheet, ctx):
    if ctx.get("type") == "momentum_swing" and ctx.get("team") == team:
        return True, ""
    pos = [_m(sheet, team, w).get("possession_pct") or 0 for w in (*SHORT, None)]
    if max(pos) >= 55 or _momentum_for(sheet, team) >= 40:
        return True, ""
    return (
        False,
        f"{ctx['club'](team)} have had at most {max(pos)}% of the ball and momentum isn't with them",
    )


def _losing_control(team, sheet, ctx):
    pos = min(_m(sheet, team, w).get("possession_pct") or 100 for w in SHORT)
    acc = min(_m(sheet, team, w).get("pass_accuracy_pct") or 100 for w in SHORT)
    chaos = max((sheet.get("chaos") or {}).get(w) or 0 for w in SHORT)
    if pos <= 50 or acc <= 75 or chaos >= CHAOTIC or _momentum_for(sheet, team) <= -30:
        return True, ""
    return (
        False,
        f"{ctx['club'](team)} still have the ball ({pos}%+) and are passing well ({acc}%+)",
    )


def _chaos(team, sheet, ctx):
    if ctx.get("type") == "chaos_spike":
        return True, ""
    chaos = max((sheet.get("chaos") or {}).get(w) or 0 for w in SHORT)
    if chaos >= CHAOTIC:
        return True, ""
    return (
        False,
        f"the chaos index is at most {chaos:.2f} in any recent window; the game is not chaotic",
    )


def _calm(team, sheet, ctx):
    chaos = min((sheet.get("chaos") or {}).get(w) or 1 for w in SHORT)
    if chaos > SETTLED:
        return False, f"the game is not settled: the chaos index is at least {chaos:.2f}"
    if team:
        acc = max(_m(sheet, team, w).get("pass_accuracy_pct") or 0 for w in _windows(ctx))
        if acc < 80:
            return False, f"{ctx['club'](team)} are completing at most {acc}% of their passes"
    return True, ""


def _deep(team, sheet, ctx):
    pos = min(_m(sheet, team, w).get("possession_pct") or 100 for w in _windows(ctx))
    if pos <= 45:
        return True, ""
    return False, f"{ctx['club'](team)} have had at least {pos}% of the ball in every recent window"


def _tired(team, sheet, ctx):
    minute = ctx.get("minute") or 0
    if minute >= 60:
        return True, ""
    return False, f"it is only minute {minute}; nothing in the data shows tiredness yet"


def _sharp(team, sheet, ctx):
    need = 100 if ctx.get("perfect") else 80
    acc = max(_m(sheet, team, w).get("pass_accuracy_pct") or 0 for w in _windows(ctx))
    if acc >= need:
        return True, ""
    return False, f"{ctx['club'](team)} are completing at most {acc}% of their passes"


def _sloppy(team, sheet, ctx):
    acc = min(_m(sheet, team, w).get("pass_accuracy_pct") or 100 for w in _windows(ctx))
    chaos = max((sheet.get("chaos") or {}).get(w) or 0 for w in SHORT)
    if acc <= 78 or chaos >= CHAOTIC:
        return True, ""
    return False, f"{ctx['club'](team)} are completing at least {acc}% of their passes"


def _threat(team, sheet, ctx):
    other = _other(sheet, team)
    for w in _windows(ctx) if ctx.get("recap") else (*SHORT, None):
        me, them = _m(sheet, team, w), _m(sheet, other, w)
        if (me.get("xg") or 0) > (them.get("xg") or 0) or (me.get("shots") or 0) >= (
            them.get("shots") or 0
        ) + 2:
            return True, ""
    return False, f"{ctx['club'](team)} are not creating more than their opponents"


def _against_run(team, sheet, ctx):
    pos = _m(sheet, team, 300).get("possession_pct") or 50
    if pos < 50 or _momentum_for(sheet, team) < 0:
        return True, ""
    return (
        False,
        f"{ctx['club'](team)} had {pos}% of the ball and the momentum: that is the run of play",
    )


def _rx(p: str) -> re.Pattern:
    return re.compile(p, re.IGNORECASE)


REASONS = [
    Reason(
        "pressing",
        _rx(
            r"\b(press|presses|pressing|pressed|high press|hunt(s|ing)? in packs|"
            r"turn(s|ing)? up the (heat|press))\b"
        ),
        _pressing,
    ),
    Reason(
        "losing control",
        _rx(
            r"\b(los(e|es|ing|t) (their |the )?(control|grip|rhythm|shape|way)|rattled|rattling|"
            r"on the ropes|under the cosh|pinned back|can't get out|rhythm broken|broken rhythm)\b"
        ),
        _losing_control,
    ),
    Reason(
        "control",
        _rx(
            r"\b(in control|tak(e|es|ing) control|took control|tak(e|es|ing) charge|dominat\w*|"
            r"on top|upper hand|bossing|run(s|ning)? the game|calling the shots|"
            r"grip on the (game|match)|scruff of the neck|held onto the ball|hold(s|ing)? on to the ball|"
            r"keep(s|ing)? the ball|most of the ball|take hold)\b"
        ),
        _control,
    ),
    Reason(
        "chaos",
        _rx(
            r"\b(chaos|chaotic|scrappy|frantic|end[- ]to[- ]end|helter[- ]skelter|ragged|unsettled|"
            r"boil(s|ing)? over|pinball|all over the place|haywire)\b"
        ),
        _chaos,
        team_needed=False,
    ),
    Reason(
        "calm",
        _rx(r"\b(calm|composed|composure|patient|patience|unhurried|settled|in no rush)\b"),
        _calm,
    ),
    Reason(
        "sitting deep",
        _rx(
            r"\b(sit(s|ting)? (deep|back|off)|park(s|ed|ing)? the bus|defend(s|ing)? deep|"
            r"low block|drop(s|ping)? deep)\b"
        ),
        _deep,
    ),
    Reason(
        "tiredness",
        _rx(
            r"\b(tired|tiring|tire|fatigue\w*|weary|heavy legs|legs (are )?(going|gone)|"
            r"running on empty|out on their feet)\b"
        ),
        _tired,
        team_needed=False,
    ),
    Reason(
        "sharp passing",
        _rx(
            r"\b(sharp|crisp|slick|perfect|precise|neat|clean|smart|quick|calm) pass(ing|es)?\b|"
            r"\bpassing (is |was )?(sharp|crisp|slick|perfect|precise)\b"
        ),
        _sharp,
    ),
    Reason(
        "sloppy passing",
        _rx(
            r"\b(sloppy|careless|loose|wayward|poor) pass(ing|es)?\b|"
            r"\bgiv(e|es|ing) (it|the ball) away\b"
        ),
        _sloppy,
    ),
    Reason(
        "creating more",
        _rx(
            r"\b(creat(e|es|ing) (more|the better|all the) chances|the better chances|"
            r"carv(e|es|ing) (them )?open|pepper(s|ing)?|knocking on the door|camped|laying siege|"
            r"(all|most) the chances)\b"
        ),
        _threat,
    ),
    Reason("against the run of play", _rx(r"\bagainst the run of play\b"), _against_run),
]


def _club_mentions(text: str, clubs: dict[str, str]) -> list[tuple[int, str]]:
    found = []
    # Every league club counts as a mention, so a line about another match is left to that match.
    league = {code: town for town, code in CLUB_CODES.items() if code not in clubs}
    for code, name in {**league, **clubs}.items():
        for alias in {name, name.split()[0], code}:
            for m in re.finditer(rf"\b{re.escape(alias)}\b", text):
                found.append((m.start(), code))
    return sorted(found)


def _team_for(text: str, start: int, end: int, mentions, default: str | None) -> str | None:
    after = text[end : end + 40]
    by = re.match(r"\s+by (the )?(\w+)", after)
    if by:
        for pos, code in mentions:
            if pos == end + by.start(2):
                return code
    before = [code for pos, code in mentions if pos < start]
    if before:
        return before[-1]
    following = [code for pos, code in mentions if pos > end]
    return following[0] if following else default


def check_reasons(
    text: str,
    sheet: dict,
    clubs: dict[str, str],
    moment_type: str | None = None,
    moment_team: str | None = None,
    minute: int | None = None,
) -> list[str]:
    """Problems with the reasons a caption gives. Empty means every reason is backed by the data."""
    mentions = _club_mentions(text, clubs)
    playing = set(sheet.get("metrics") or {})
    recap = bool(moment_type and moment_type.endswith("_recap"))
    problems = []
    seen = set()
    for reason in REASONS:
        for m in reason.pattern.finditer(text):
            if NEGATION.search(text[max(0, m.start() - 40) : m.start()]) or FADING.search(
                text[m.end() :]
            ):
                continue  # "can't get out", "the press has lost its bite": a different claim, left alone
            team = _team_for(text, m.start(), m.end(), mentions, moment_team)
            if team is not None and team not in playing:
                continue  # a club in another fixture: the stats engine only watches this match
            ctx = {
                "type": moment_type,
                "team": moment_team,
                "minute": minute,
                "recap": recap,
                "perfect": "perfect" in m.group(0).lower(),
                "club": lambda code: clubs.get(code or "", code or "they"),
            }
            if reason.team_needed and team is None:
                ok = any(reason.test(t, sheet, ctx)[0] for t in playing)
                why = "no club in the match fits it"
            else:
                ok, why = reason.test(team, sheet, ctx)
            key = (reason.name, team)
            if not ok and key not in seen:
                seen.add(key)
                problems.append(f"reason not backed by the data: '{m.group(0)}' ({why})")
    return problems
