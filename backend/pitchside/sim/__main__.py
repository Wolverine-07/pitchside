"""Generate synthetic matches as JSON Lines.

uv run python -m pitchside.sim --seed 16 --storyline comeback --out ../data/samples/demo.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .engine import STORYLINES, simulate

DEMO_SEED = 16  # comeback storyline: RVA score early, KSC win 2-1 with goals at 68' and 71'


def summarize(events: list[dict]) -> str:
    counts = Counter(e["type"] for e in events)
    passes = [e for e in events if e["type"] == "pass"]
    done = sum(e["outcome"] == "complete" for e in passes)
    xg = Counter()
    for e in events:
        if e["type"] == "shot":
            xg[e["team"]] += e["xg"]
    score = events[-1]["data"]["score"]
    goals = ", ".join(f"{e['team']} {e['minute']}'" for e in events if e["type"] == "goal")
    return (
        f"{events[0]['match_id']}: KSC {score['KSC']} - {score['RVA']} RVA ({goals or 'no goals'})\n"
        f"  events {len(events)}, passes {len(passes)} ({done / len(passes):.0%} complete), "
        f"shots {counts['shot']}, xG KSC {xg['KSC']:.2f} / RVA {xg['RVA']:.2f}, "
        f"fouls {counts['foul']}, cards {counts['card']}, corners {counts['corner']}"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m pitchside.sim", description=__doc__.splitlines()[0]
    )
    ap.add_argument("--seed", type=int, default=DEMO_SEED)
    ap.add_argument("--storyline", choices=sorted(STORYLINES), default="none")
    ap.add_argument("--out", type=Path, help="write events here as JSON Lines")
    args = ap.parse_args(argv)

    events = simulate(args.seed, args.storyline)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w") as f:
            for e in events:
                f.write(json.dumps(e, separators=(",", ":")) + "\n")
    print(summarize(events), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
