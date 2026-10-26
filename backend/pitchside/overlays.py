"""Timed, machine-readable overlays: the product's real output.

The React app is one renderer; a broadcast graphics partner could consume the
same stream. Field names match schemas/overlay.schema.json.
"""

from __future__ import annotations

import itertools
import re

from pitchside.stats.state import Moment

SLOTS = {
    "score_bug": "top_left",
    "player_tag": "on_pitch",
    "stat_strip": "bottom",
    "insight_card": "lower_third",
    "momentum_strip": "bottom",
    "recap_card": "full",
}
DEFAULT_MS = {
    "insight_card": 9000,
    "player_tag": 5000,
    "stat_strip": 7000,
    "recap_card": 20000,
    "score_bug": 0,
    "momentum_strip": 0,
}
_ids = itertools.count(1)


def overlay(
    type_: str,
    match_id: str,
    anchor_t_ms: int,
    content: dict,
    *,
    start_t_ms: int | None = None,
    priority: int = 50,
    profile_key: str = "*",
    moment_id: str | None = None,
    provenance: dict | None = None,
) -> dict:
    return {
        "overlay_id": f"ov-{next(_ids):05d}",
        "match_id": match_id,
        "moment_id": moment_id,
        "type": type_,
        "slot": SLOTS[type_],
        "anchor_t_ms": anchor_t_ms,
        "start_t_ms": start_t_ms if start_t_ms is not None else anchor_t_ms,
        "duration_ms": DEFAULT_MS[type_],
        "priority": priority,
        "profile_key": profile_key,
        "content": content,
        "provenance": provenance or {"verified": True, "source": "stats_engine"},
    }


CLUB_NAMES = (
    "Kingsport City",
    "Riverside Athletic",
    "Ashvale United",
    "Brightwater FC",
    "Coldharbour Town",
    "Dunmore Albion",
    "Eastmere Wanderers",
    "Fairhaven Forest",
    "Kingsport",
    "Riverside",
    "Ashvale",
    "Brightwater",
    "Coldharbour",
    "Dunmore",
    "Eastmere",
    "Fairhaven",
)


def tidy(text: str) -> str:
    """Capitalise the first letter and the club names; models sometimes lower-case them."""
    for name in CLUB_NAMES:
        text = re.sub(rf"\b{name}\b", name, text, flags=re.IGNORECASE)
    return text[:1].upper() + text[1:]


def insight_card(
    m: Moment,
    match_id: str,
    headline: str,
    body: str,
    lang: str,
    profile_key: str,
    start_t_ms: int,
    agents: list[str],
    verified: bool,
    fallback: bool,
    trace_id: str | None = None,
) -> dict:
    return overlay(
        "insight_card",
        match_id,
        m.t_ms,
        {
            "headline": tidy(headline),
            "body": tidy(body),
            "lang": lang,
            "moment_type": m.type,
            "team": m.team,
            "player": m.player,
            "evidence": [e.__dict__ for e in m.evidence],
        },
        start_t_ms=start_t_ms,
        priority=m.significance,
        profile_key=profile_key,
        moment_id=m.id,
        provenance={
            "verified": verified,
            "fallback": fallback,
            "agents": agents,
            "trace_id": trace_id,
        },
    )


def player_tag(match_id: str, ev: dict, name: str) -> dict:
    return overlay(
        "player_tag",
        match_id,
        ev["t_ms"],
        {
            "player": ev["player"],
            "name": name,
            "speed_kmh": ev.get("speed_kmh"),
            "x": ev.get("x"),
            "y": ev.get("y"),
        },
        priority=30,
    )
