"""A/B test: one agent vs the Pitchside agent team, on the same moments.

Both sides use the same model and the same stats tools. The single agent gets a
moment and writes the on-screen caption in one go. Pitchside runs its full
workflow. Every caption is then checked by the same deterministic rules:

- wrong number: a number that matches nothing the stats engine knows at that moment
- wrong name:   a player named who is not part of the moment
- wrong time:   end-of-match talk before the 80th minute, or singular club verbs

    uv run python evals/ab_test.py --seeds 16:comeback,3,7,11,21 --out evals/results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from agent_framework import Agent

from pitchside.agents.llm import clients
from pitchside.agents.pipeline import ask
from pitchside.agents.verify import check_context, check_names, check_numbers
from pitchside.runner import Broadcast
from pitchside.sim.engine import simulate
from pitchside.tools import StatsTools

SINGLE_AGENT = """You are an AI football commentator for a live broadcast. A moment has been flagged.
Use the tools to look up any numbers you need, then write the on-screen caption: a headline of at most six
words and one line of at most 22 words explaining why the moment matters.
Reply with JSON only: {"headline": "...", "line": "..."}"""


def audit(text: str, sheet: dict, moment, names: dict[str, str]) -> dict:
    """Check a caption against everything the stats engine knew (a generous truth set)."""
    truth = {
        "sheet": sheet,
        "evidence": [e.__dict__ for e in moment.evidence],
        "minute": moment.minute,
    }
    players = {"players": [moment.player] if moment.player else [], **truth}
    return {
        "wrong_number": bool(check_numbers(text, truth)),
        "wrong_name": bool(check_names(text, players, names)),
        "wrong_context": bool(check_context(text, moment.minute)),
    }


async def run_match(seed: int, storyline: str, fast, deep) -> dict:
    events = simulate(seed, storyline)
    b = Broadcast(events, fast, ["casual"], ["en"], deep_client=deep)
    single = Agent(fast, SINGLE_AGENT, name="SingleAgent", tools=b.tools.agent_tools())
    rows, cards = [], {}
    async for item in b.run():
        if item["kind"] == "overlay" and item["overlay"]["type"] == "insight_card":
            c = item["overlay"]["content"]
            cards[item["overlay"]["moment_id"]] = f"{c['headline']}. {c['body']}"
        if item["kind"] != "trace":
            continue
        # The pipeline just aired this moment. Ask the single agent about the same moment, same state.
        job_moment = next(m for m in b.state.moments if m.id == item["trace"]["moment_id"])
        card = cards.get(job_moment.id)
        sheet = StatsTools(b.state).fact_sheet([p for p in [job_moment.player] if p])
        t0 = time.perf_counter()
        reply = await ask(
            single,
            json.dumps(
                {"moment": job_moment.to_dict(), "player_name": b.state.name(job_moment.player)}
            ),
        )
        single_s = time.perf_counter() - t0
        single_text = (
            f"{(reply or {}).get('headline', '')}. {(reply or {}).get('line', '')}" if reply else ""
        )
        steps = item["trace"]["steps"]
        rows.append(
            {
                "seed": seed,
                "minute": job_moment.minute,
                "type": job_moment.type,
                "single": {
                    "text": single_text,
                    "seconds": round(single_s, 1),
                    **audit(single_text, sheet, job_moment, b.state.names),
                }
                if reply
                else None,
                "pipeline": {
                    "text": card,
                    "seconds": round(sum(s["ms"] for s in steps) / 1000, 1),
                    "drafts_rejected": sum(
                        s["agent"] == "verifier" and s["status"] == "reject" for s in steps
                    ),
                    "template": any(s["agent"] == "template" for s in steps),
                    **(audit(card or "", sheet, job_moment, b.state.names)),
                },
            }
        )
    return {"seed": seed, "storyline": storyline, "moments": rows}


def summarize(matches: list[dict]) -> dict:
    rows = [r for m in matches for r in m["moments"] if r["single"]]
    n = len(rows)

    def rate(side: str, key: str) -> float:
        return round(100 * sum(r[side][key] for r in rows) / n, 1) if n else 0.0

    def any_err(side: str) -> float:
        bad = sum(
            r[side]["wrong_number"] or r[side]["wrong_name"] or r[side]["wrong_context"]
            for r in rows
        )
        return round(100 * bad / n, 1) if n else 0.0

    return {
        "moments": n,
        "single_agent": {
            "wrong_number_pct": rate("single", "wrong_number"),
            "wrong_name_pct": rate("single", "wrong_name"),
            "wrong_context_pct": rate("single", "wrong_context"),
            "any_error_pct": any_err("single"),
            "avg_seconds": round(sum(r["single"]["seconds"] for r in rows) / n, 1) if n else 0,
        },
        "pitchside": {
            "wrong_number_pct": rate("pipeline", "wrong_number"),
            "wrong_name_pct": rate("pipeline", "wrong_name"),
            "wrong_context_pct": rate("pipeline", "wrong_context"),
            "any_error_pct": any_err("pipeline"),
            "drafts_caught_by_verifier": sum(r["pipeline"]["drafts_rejected"] for r in rows),
            "template_fallbacks": sum(r["pipeline"]["template"] for r in rows),
            "avg_seconds": round(sum(r["pipeline"]["seconds"] for r in rows) / n, 1) if n else 0,
        },
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="16:comeback,3,7,11,21")
    ap.add_argument("--out", default="evals/results.json")
    args = ap.parse_args()
    c = clients()
    if c["fast"] is None:
        raise SystemExit("Set PITCHSIDE_PROVIDER to a real model to run the A/B test.")
    matches = []
    for spec in args.seeds.split(","):
        seed, _, story = spec.partition(":")
        print(f"seed {seed} {story or 'none'} ...", flush=True)
        matches.append(await run_match(int(seed), story or "none", c["fast"], c["deep"]))
        print(json.dumps(summarize(matches), indent=2), flush=True)
    result = {"summary": summarize(matches), "matches": matches}
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    asyncio.run(main())
