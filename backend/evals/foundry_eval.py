"""Score the A/B captions with Microsoft Foundry's built-in evaluators.

Reads evals/results.json (from ab_test.py), rebuilds the exact facts each caption
was written from (the simulation is deterministic, so replaying a seed gives the
same match state at every moment), and runs Foundry's groundedness, relevance,
coherence and fluency evaluators on both sides. Results appear in the Foundry
portal under Evaluations.

    FOUNDRY_PROJECT_ENDPOINT=... uv run python evals/foundry_eval.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from agent_framework import EvalItem, Message
from agent_framework.foundry import FoundryChatClient, FoundryEvals
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

from pitchside.sim.engine import simulate
from pitchside.stats.state import MatchState

load_dotenv()

EVALUATORS = [
    FoundryEvals.GROUNDEDNESS,
    FoundryEvals.RELEVANCE,
    FoundryEvals.COHERENCE,
    FoundryEvals.FLUENCY,
]


def contexts(seed: int, storyline: str) -> dict[tuple[int, str], str]:
    """Facts available at each flagged moment, keyed by (minute, type)."""
    st = MatchState()
    out: dict[tuple[int, str], str] = {}
    for ev in simulate(seed, storyline):
        for m in st.ingest(ev):
            names = {p: st.name(p) for p in {m.player, *(e.player for e in m.evidence)} if p}
            facts = {
                "moment": m.to_dict(),
                "player_names": names,
                "clubs": {"KSC": "Kingsport City", "RVA": "Riverside Athletic"},
                "match_minute": m.minute,
                "snapshot": st.snapshot(),
                # Everything the agents' tools could return at this moment, so the judge is fair.
                "last_3_minutes": {t: st.team_metrics(t, 180) for t in st.teams},
                "last_5_minutes": {t: st.team_metrics(t, 300) for t in st.teams},
                "last_10_minutes": {t: st.team_metrics(t, 600) for t in st.teams},
                "whole_match": {t: st.team_metrics(t) for t in st.teams},
                "chaos_index": {f"last_{w}_s": st.chaos(w) for w in (180, 300, 600)},
                "players": {
                    pid: {k: v for k, v in st.player_summary(pid).items() if v}
                    for pid in st.names
                    if st.player[pid] or pid in st.physical
                },
            }
            out.setdefault((m.minute, m.type), json.dumps(facts))
    return out


def items_for(side: str, results: dict) -> list[EvalItem]:
    items = []
    cache: dict[int, dict] = {}
    for match in results["matches"]:
        seed, story = match["seed"], match["storyline"]
        ctx = cache.setdefault(seed, contexts(seed, story))
        for r in match["moments"]:
            text = (r.get(side) or {}).get("text")
            facts = ctx.get((r["minute"], r["type"]))
            if not text or not facts:
                continue
            query = (
                f"Write the on-screen caption for this live football moment ({r['type'].replace('_', ' ')}, "
                f"minute {r['minute']}), explaining why it matters, using only the match facts provided."
            )
            items.append(
                EvalItem(
                    conversation=[Message("user", [query]), Message("assistant", [text])],
                    context=facts,
                )
            )
    return items


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="captions per side (0 = all)")
    args = ap.parse_args()
    results = json.loads(Path("evals/results.json").read_text())
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini"),
        credential=AzureCliCredential(),
    )
    evals = FoundryEvals(client=client, evaluators=EVALUATORS, timeout=900)
    summary = {}
    for side, label in (("single", "single agent"), ("pipeline", "Pitchside agent team")):
        items = items_for(side, results)
        if args.limit:
            items = items[: args.limit]
        print(f"{label}: {len(items)} captions", flush=True)
        res = await evals.evaluate(items, eval_name=f"Pitchside A/B: {label}")
        failures = [
            {
                "caption": it.output_text,
                "scores": [
                    {"name": s.name, "score": s.score, "passed": s.passed, "sample": s.sample}
                    for s in it.scores
                ],
            }
            for it in (res.items or [])
            if it.is_failed
        ]
        summary[label] = {
            "failures": failures,
            "status": res.status,
            "counts": res.result_counts,
            "per_evaluator": res.per_evaluator,
            "report_url": res.report_url,
            "error": res.error,
        }
        print(
            json.dumps({k: v for k, v in summary[label].items() if k != "failures"}, indent=2),
            flush=True,
        )
    Path("evals/foundry_results.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
