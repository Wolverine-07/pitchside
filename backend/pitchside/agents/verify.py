"""Deterministic checks the Verifier agent runs before anything goes on air.

Numbers: every number in a line must match a fact the stats engine produced.
Names: a player named in the line must be one the facts are about.
Style: no chatbot phrases, no emoji, short enough for a live caption.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
    "once": 1,
    "twice": 2,
    "half": None,
    "first": None,
    "second": None,
}
BANNED = [
    "delve",
    "testament to",
    "it's worth noting",
    "it is worth noting",
    "in conclusion",
    "tapestry",
    "in the realm of",
    "game-changer",
    "showcasing",
    "a true masterclass",
    "let's dive",
    "unleash",
    "elevate",
]
EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿]")
NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?:st|nd|rd|th)?(?![\w])")
MAX_WORDS_LIVE = 32


@dataclass
class Check:
    ok: bool
    problems: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


def numbers_in(text: str) -> list[float]:
    found = [float(n) for n in NUM.findall(text.replace(",", ""))]
    for word in re.findall(r"[a-z]+", text.lower()):
        v = NUMBER_WORDS.get(word)
        if v is not None:
            found.append(float(v))
    return found


def allowed_numbers(facts: dict) -> set[float]:
    """Every number the facts contain, plus the obvious ways a commentator restates them."""
    out: set[float] = set()

    def add(v) -> None:
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            out.add(round(float(v), 1))
            out.add(float(round(v)))
            out.add(abs(round(float(v), 1)))  # "momentum -54" is said as "54"
            out.add(float(abs(round(v))))
            if isinstance(v, float) and 0 < v < 1:
                out.add(float(round(v * 100)))  # 0.62 -> 62%
        elif isinstance(v, str):
            for n in numbers_in(v):
                out.add(n)
        elif isinstance(v, dict):
            for k, x in v.items():
                if k in {"window_s"} and isinstance(x, (int, float)):
                    out.add(float(x))
                    out.add(float(round(x / 60)))  # 600 s -> 10 minutes
                add(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                add(x)

    add(facts)
    return out


def check_numbers(text: str, facts: dict) -> list[str]:
    allowed = allowed_numbers(facts)
    problems = []
    for n in numbers_in(text):
        if not any(abs(n - a) <= 0.51 for a in allowed):
            problems.append(f"number {n:g} is not in the stats engine's facts")
    return problems


def check_names(text: str, facts: dict, roster: dict[str, str]) -> list[str]:
    """roster maps player id -> full name. Named players must be ones the facts mention."""
    mentioned_ids = set(re.findall(r"[A-Z]{3}-\d{2}", str(facts)))
    allowed = {roster[i] for i in mentioned_ids if i in roster}
    problems = []
    for name in roster.values():
        surname = name.split()[-1]
        if re.search(rf"\b{re.escape(surname)}\b", text) and name not in allowed:
            problems.append(f"{name} is named but is not part of this moment")
    return problems


def check_style(text: str, live: bool = True) -> list[str]:
    problems = []
    low = text.lower()
    for phrase in BANNED:
        if phrase in low:
            problems.append(f"chatbot phrase: '{phrase}'")
    if EMOJI.search(text):
        problems.append("emoji")
    if text.count("!") > 1:
        problems.append("too many exclamation marks")
    if live and len(text.split()) > MAX_WORDS_LIVE:
        problems.append(f"too long for a live caption ({len(text.split())} words)")
    return problems


def check_citations(
    numbers: list[dict], sheet: dict, evidence: list[dict]
) -> tuple[list[dict], list[str]]:
    """Keep only the Analyst's cited numbers that match the stats engine exactly, by metric name.

    sheet is StatsTools.fact_sheet(); evidence is the moment's own evidence list.
    """
    kept, problems = [], []
    for n in numbers:
        metric, value = n.get("metric"), n.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        truth = _lookup(metric, n.get("team"), n.get("player"), n.get("window_s"), sheet, evidence)
        if (
            truth is not None
            and isinstance(truth, (int, float))
            and abs(float(truth) - float(value)) <= 0.051
        ):
            kept.append(n)
        else:
            problems.append(f"{metric}={value} does not match the stats engine ({truth})")
    return kept, problems


def _lookup(metric, team, player, window_s, sheet: dict, evidence: list[dict]):
    for e in evidence:
        if e.get("metric") == metric and (team is None or e.get("team") in (None, team)):
            return e.get("value")
    if metric in ("live_position", "position", "points", "gd") and team in sheet.get("league", {}):
        return sheet["league"][team].get("live_position" if metric == "position" else metric)
    if player and player in sheet.get("players", {}):
        return sheet["players"][player].get(metric)
    snap = sheet.get("snapshot", {})
    if metric in snap and not isinstance(snap[metric], dict):
        return snap[metric]
    if metric in snap and isinstance(snap[metric], dict) and team:
        return snap[metric].get(team)
    if metric == "chaos_index":
        return sheet.get("chaos", {}).get(window_s or 300)
    if team and team in sheet.get("metrics", {}):
        return sheet["metrics"][team].get(window_s, {}).get(metric)
    return None


END_OF_MATCH = re.compile(
    r"\b(closing (minutes|stages)|final (minutes|five|stages|whistle|moments)|dying (minutes|seconds)|"
    r"frantic finish|with (just )?minutes (left|to go)|late in the (game|match)|late on|"
    r"late (rally|surge|drama|chaos|push|scramble|pressure|show|charge|siege|winner|equaliser)|"
    r"(rally|surge|push|control|chaos|drama|pressure) late)\b",
    re.IGNORECASE,
)
SINGULAR_CLUB = re.compile(
    r"\b(Kingsport|Riverside|Ashvale|Brightwater|Coldharbour|Dunmore|Eastmere|Fairhaven)"
    r"( City| Athletic| United| FC| Town| Albion| Wanderers| Forest)? (is|was|has|wins|keeps|holds|takes|looks|pushes|presses|"
    r"battles|struggles|finds|makes|scores|leads|trails|dominates|controls|boasts|suffers|raises|drives|"
    r"seizes|grabs|needs|wants|shows|sits|plays|goes|turns|seems|remains|stays|gets|loses|misses)\b"
)


AT_MINUTES = re.compile(r"\bat (the )?\d+ minutes?\b", re.IGNORECASE)
MINUTE_ORDINAL = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th) minute\b", re.IGNORECASE)
HALF_HOUR = re.compile(r"\bhalf[- ]an[- ]hour\b|\bhalf-hour\b|\bhalf hour\b", re.IGNORECASE)


def _minutes_in(facts: dict) -> set[int]:
    """Minutes the facts refer to: goal times, another match's minute."""
    found: set[int] = set()

    def walk(v) -> None:
        if isinstance(v, dict):
            if v.get("metric") in ("goal_minute", "other_match_minute") and isinstance(
                v.get("value"), int
            ):
                found.add(v["value"])
            if "minute" in v and isinstance(v["minute"], int):
                found.add(v["minute"])
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(facts)
    return found


def check_context(
    text: str, minute: int | None, known_minutes: set[int] | None = None
) -> list[str]:
    """Things a model gets wrong that a viewer notices at once.

    known_minutes: other minutes the facts mention (goal times, another match's clock), which a
    caption may legitimately refer to, as a recap does."""
    problems = []
    known = known_minutes or set()
    if minute is not None and minute < 80 and END_OF_MATCH.search(text):
        problems.append(f"talks about the end of the match, but it is only minute {minute}")
    m = SINGULAR_CLUB.search(text)
    if m:
        problems.append(f"'{m.group(0)}': clubs take plural verbs in British English")
    if AT_MINUTES.search(text):
        problems.append('say "in the 41st minute", not "at 41 minutes"')
    if minute is not None:
        for said in MINUTE_ORDINAL.findall(text):
            if abs(int(said) - minute) > 1 and int(said) not in known:
                problems.append(f"says minute {said}, but this moment is in minute {minute}")
        if HALF_HOUR.search(text) and not 25 <= minute <= 40:
            problems.append(f"mentions the half-hour, but it is minute {minute}")
    return problems


JARGON = re.compile(
    r"\b(ppda|xg|kph|tempo of|chaos index|window_s|regains_opp_half)\b", re.IGNORECASE
)


def check_audience(text: str, profile: str, max_numbers: int = 2) -> list[str]:
    """Analysts get the numbers; everyone else gets the story."""
    if profile.startswith("analyst"):
        return []
    kind = profile.split(":")[0]
    problems = []
    jargon = JARGON.search(text)
    if jargon:
        problems.append(f"stats jargon '{jargon.group(0)}' in a {kind} caption")
    if len(NUM.findall(text)) > max_numbers:
        problems.append(f"more than {max_numbers} numbers in a {kind} caption")
    return problems


TOP_OF_TABLE = re.compile(
    r"\b(leads?|leading|tops?|topping|top of|summit of|on top of) the (table|league|standings)\b",
    re.IGNORECASE,
)


def _positions(facts) -> set:
    """Every live table position the facts mention."""
    found = set()
    if isinstance(facts, dict):
        if facts.get("metric") == "live_position":
            found.add(facts.get("value"))
        for v in facts.values():
            found |= _positions(v)
    elif isinstance(facts, list):
        for v in facts:
            found |= _positions(v)
    return found


def check_table(text: str, facts: dict) -> list[str]:
    """'Lead the table' is only true for whoever is 1st."""
    m = TOP_OF_TABLE.search(text)
    if m and 1 not in _positions(facts):
        return [f"'{m.group(0)}' but no club in the facts is 1st"]
    return []


def verify(text: str, facts: dict, roster: dict[str, str], live: bool = True) -> Check:
    moment = facts.get("moment")
    minute = moment.get("minute") if isinstance(moment, dict) else None
    problems = (
        check_numbers(text, facts)
        + check_names(text, facts, roster)
        + check_style(text, live)
        + check_context(text, minute, _minutes_in(facts))
        + check_table(text, facts)
        + check_leader(text, facts.get("score") if isinstance(facts.get("score"), dict) else None)
    )
    return Check(not problems, problems)


SCRIPTS = {
    "hi": re.compile("[\u0900-\u097f]"),
    "ar": re.compile("[\u0600-\u06ff]"),
    "ja": re.compile("[\u3040-\u30ff\u4e00-\u9fff]"),
}


def check_language(text: str, lang: str) -> list[str]:
    """Models sometimes answer in English when asked for Hindi, Arabic or Japanese."""
    script = SCRIPTS.get(lang)
    if script and len(script.findall(text)) < len(text) / 4:
        return [f"not written in the {lang} script"]
    return []


REAL_WORLD = re.compile(
    r"\b(Premier League|Champions League|Manchester|Arsenal|Chelsea|Liverpool|Tottenham|Everton|"
    r"Newcastle|Aston Villa|West Ham|Brighton|Wolves|Fulham|Brentford|Crystal Palace|Nottingham|"
    r"Bournemouth|Leicester|Leeds|Burnley|Sunderland|Man (United|Utd|City)|Spurs|Gunners|"
    r"Real Madrid|Barcelona|Bayern|Juventus|PSG|La Liga|Serie A|Bundesliga)\b",
    re.IGNORECASE,
)


def check_real_world(text: str) -> list[str]:
    """Pitchside is a fictional league: real clubs and competitions never appear in what it says."""
    m = REAL_WORLD.search(text)
    return [f"names a real club or competition ('{m.group(0)}')"] if m else []


CLUB_CODES = {
    "Kingsport": "KSC",
    "Riverside": "RVA",
    "Ashvale": "AVU",
    "Brightwater": "BWF",
    "Coldharbour": "CHT",
    "Dunmore": "DMA",
    "Eastmere": "EMW",
    "Fairhaven": "FHF",
}
LEADER = re.compile(
    rf"\b({'|'.join([*CLUB_CODES, *CLUB_CODES.values()])})"
    r"( City| Athletic| United| FC| Town| Albion| Wanderers| Forest)?"
    r" (are |is |have |go |went |now )?(ahead|in front|leads?|leading|trail|trailing|behind|chasing)\b",
)
NOT_THE_SCORE = re.compile(r" (the|in|on|for|with) ")  # "lead the table", "lead in possession"


def check_leader(text: str, score: dict[str, int] | None) -> list[str]:
    """'Kingsport are ahead' must match the score. Clubs in other matches are left alone."""
    if not score:
        return []
    problems = []
    for m in LEADER.finditer(text):
        code = CLUB_CODES.get(m.group(1), m.group(1))
        if code not in score:
            continue
        other = max((v for k, v in score.items() if k != code), default=0)
        ahead = m.group(4) in ("ahead", "in front", "lead", "leads", "leading")
        if m.group(4).startswith("lead") and NOT_THE_SCORE.match(text, m.end()):
            continue
        if (ahead and score[code] <= other) or (not ahead and score[code] >= other):
            problems.append(f"'{m.group(0)}' but the score is {score}")
    return problems


SCORELINE = re.compile(r"\b(\d+)\s?[-–]\s?(\d+)\b(?!\s?(min|'|th|st|nd|rd))")
CLUB = re.compile(rf"\b({'|'.join([*CLUB_CODES, *CLUB_CODES.values()])})\b")


def scorelines(goals: list[str], teams: list[str]) -> set[tuple[str, int, int]]:
    """Every score this match has been at, as (club, its goals, the other's goals)."""
    a, b = teams
    score = {a: 0, b: 0}
    seen = set()
    for team in [None, *goals]:
        if team:
            score[team] += 1
        seen |= {(a, score[a], score[b]), (b, score[b], score[a])}
    return seen


def check_scorelines(text: str, goals: list[str], teams: list[str]) -> list[str]:
    """A scoreline about one of this match's clubs must be a score the match has actually been at.

    Each scoreline belongs to the nearest club named before it in the same sentence (or just after
    it, as in "a 2-0 win for Riverside"); scorelines about other matches are left alone.
    """
    seen = scorelines(goals, teams)
    problems = []
    for m in SCORELINE.finditer(text):
        before = re.split(r"[.;!?]", text[max(0, m.start() - 60) : m.start()])[-1]
        named = CLUB.findall(before)
        if not named:
            named = CLUB.findall(re.split(r"[.;!?,]", text[m.end() : m.end() + 30])[0])[:1]
        if not named:
            continue
        code = CLUB_CODES.get(named[-1], named[-1])
        if code not in teams:
            continue
        x, y = int(m.group(1)), int(m.group(2))
        if (code, x, y) not in seen and (code, y, x) not in seen:
            problems.append(f"'{m.group(0)}' is not a score this match has been at")
    return problems


SENT_OFF = re.compile(
    r"\b(sent off|sending[- ]off|red card(ed)?|sees red|saw red|seen red|dismissed|down to (ten|10) men)\b",
    re.IGNORECASE,
)
DENIED = re.compile(
    r"\b(no|not|never|nobody|no one|n't|without|yet to|isn't|wasn't|hasn't|hadn't)\b[^.]{0,30}$",
    re.IGNORECASE,
)


def check_cards(text: str, cards: list[dict]) -> list[str]:
    """Saying someone was sent off needs a red card in the match events."""
    if any(c.get("card") == "red" for c in cards):
        return []
    for m in SENT_OFF.finditer(text):
        before = text[max(0, m.start() - 40) : m.start()].replace("n't", " n't")
        if not DENIED.search(before):
            return [f"'{m.group(0)}' but nobody has been sent off"]
    return []
