"""Grade the smallest edits several times, to see how steady the pass rates are.

    python study/judges/repeat.py --trials 3

The first run graded each control once. The rates it found for an answer
with one sentence removed, 40 to 53%, could move on a rerun. This grades the
reference and the smallest edit of each kind, and nothing else, three times.

It runs through the Claude Code command line on a subscription (see
claude_code.py), so its numbers are kept in results-repeat/ and are not
mixed with the API run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import claude_code  # noqa: E402, F401  registers the claude-code model
from judges import JUDGES  # noqa: E402
from run import SETS, task_for  # noqa: E402

from knownbad import build  # noqa: E402
from knownbad.cli import make_result  # noqa: E402
from knownbad.inspect_adapter import items_from, run_task  # noqa: E402
from knownbad.io import write_json  # noqa: E402

SMALLEST = ("drop", "splice", "numbers", "flip", "contradict")


def smallest_edits(controls: list) -> list:
    return [
        c
        for c in controls
        if c.family == "reference" or (c.family in SMALLEST and (c.edits or 1) == 1)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--model", default="haiku", help="a Claude Code model name")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--only", help="run only cells whose name contains this text")
    parser.add_argument("--limit", type=int, help="grade only the first N controls of a cell")
    parser.add_argument("--out", default="results-repeat")
    args = parser.parse_args()

    out_dir = HERE / args.out
    out_dir.mkdir(exist_ok=True)
    for judge in JUDGES:
        for set_name in SETS:
            name = f"{set_name}__{judge}__claude-code-{args.model}"
            path = out_dir / f"{name}.json"
            if args.only and args.only not in name:
                continue
            if path.exists():
                print(f"done     {name}", flush=True)
                continue
            task = task_for(set_name, judge, 1, dry_run=False)
            items, samples = items_from(task)
            controls = smallest_edits(build(items))[: args.limit]
            try:
                outcomes, usage = run_task(
                    task,
                    controls,
                    samples,
                    model=f"claude-code/{args.model}",
                    trials=args.trials,
                    max_connections=args.workers,
                )
            except claude_code.LimitReached as stop:
                print(f"stopped  {name}: {stop}", flush=True)
                return 3
            result = make_result(
                outcomes,
                {i.id: i for i in items},
                f"{judge} · claude-code {args.model}",
                args.trials,
                usage,
            )
            summary = result["summary"]
            tokens = sum(u["input_tokens"] + u["output_tokens"] for u in usage.values())
            print(
                f"ran      {name}: {summary['controls']} controls × {args.trials}, "
                f"{summary['errors']} without a verdict, {tokens:,} tokens",
                flush=True,
            )
            # A cell where the limit cut most calls short is not kept: the next run redoes it.
            if summary["errors"] > summary["controls"] / 4:
                print(f"stopped  {name}: too many calls without a verdict", flush=True)
                return 3
            write_json(path, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
