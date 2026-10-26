"""Run a whole match through the pipeline and print what would go on air.

uv run python -m pitchside.run --seed 16 --storyline comeback --profiles casual,analyst,club:RVA --langs en,hi
"""

from __future__ import annotations

import argparse
import asyncio
import time
from collections import Counter

from pitchside.agents.llm import clients, config
from pitchside.runner import Broadcast
from pitchside.sim.engine import simulate


async def main(args: argparse.Namespace) -> None:
    cfg = config()
    print(f"provider: {cfg.provider} {cfg.model or ''}")
    events = simulate(args.seed, args.storyline)
    c = clients()
    show = args.profiles.split(",")[0] + ":" + args.langs.split(",")[0]
    b = Broadcast(
        events, c["fast"], args.profiles.split(","), args.langs.split(","), deep_client=c["deep"]
    )
    t0, steps, cards, fallbacks = time.perf_counter(), Counter(), 0, 0
    async for item in b.run():
        if item["kind"] == "overlay" and item["overlay"]["type"] == "insight_card":
            ov = item["overlay"]
            cards += 1
            fallbacks += ov["provenance"]["fallback"]
            if ov["profile_key"] == show:
                print(
                    f"{item['minute']:>3}'  {ov['content']['headline']:<28} {ov['content']['body']}"
                )
        elif item["kind"] == "trace":
            steps.update(f"{s['agent']}:{s['status']}" for s in item["trace"]["steps"])
    print(f"\n{cards} cards in {time.perf_counter() - t0:.1f}s, {fallbacks} from templates")
    print("agent steps:", dict(sorted(steps.items())))
    print("final:", b.state.snapshot())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=16)
    ap.add_argument("--storyline", default="comeback")
    ap.add_argument("--profiles", default="casual")
    ap.add_argument("--langs", default="en")
    asyncio.run(main(ap.parse_args()))
