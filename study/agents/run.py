"""Grade broken agent runs with published judges of agent runs.

    python study/agents/run.py --limit 6 --out results-pilot   # a pilot
    python study/agents/run.py                                 # three trials of everything

It runs through the Claude Code command line on a Claude subscription, with
Claude Haiku 5.5 as the judge model (see ../judges/claude_code.py). Each cell
is one judge on one item set, kept as a normal knownbad result file, so a
stopped run resumes and every cell opens with `knownbad report`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent / "judges"))

import claude_code  # noqa: E402  registers the claude-code model
from inspect_ai import Task  # noqa: E402
from inspect_ai.dataset import MemoryDataset, Sample  # noqa: E402
from run_judges import JUDGES  # noqa: E402

from knownbad import build  # noqa: E402
from knownbad.cli import make_result  # noqa: E402
from knownbad.inspect_adapter import items_from, run_task  # noqa: E402
from knownbad.io import read_jsonl, write_json  # noqa: E402

SETS = {
    "support": HERE.parent.parent / "examples" / "agent" / "items.jsonl",
    "ops": HERE / "sets" / "ops.jsonl",
    "finance": HERE / "sets" / "finance.jsonl",
}
# The reference, another item's run, and each run family at its smallest edit.
GRADED = (
    "reference",
    "transplant",
    "run-no-action",
    "run-skipped-action",
    "run-failed-action",
    "run-args",
    "run-extra-action",
)


def task_for(set_name: str) -> Task:
    samples = [
        Sample(
            id=row["id"],
            input=row["input"],
            target=json.dumps(row["reference"]),
            metadata={"kind": row["kind"], "required_tools": row["required_tools"]},
        )
        for row in read_jsonl(SETS[set_name])
    ]
    return Task(dataset=MemoryDataset(samples))


def graded(controls: list) -> list:
    return [c for c in controls if c.family in GRADED and (c.edits or 1) == 1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--model", default="haiku", help="a Claude Code model name")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--only", help="run only cells whose name contains this text")
    parser.add_argument("--limit", type=int, help="grade only the first N items of a set")
    parser.add_argument("--out", default="results")
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
            task = task_for(set_name)
            items, samples = items_from(task)
            controls = graded(build(items))
            if args.limit:
                keep = {i.id for i in items[: args.limit]}
                controls = [c for c in controls if c.item_id in keep]
            task = Task(dataset=task.dataset, scorer=JUDGES[judge]())
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
            if summary["errors"] > summary["controls"] / 4:
                print(f"stopped  {name}: too many calls without a verdict", flush=True)
                return 3
            write_json(path, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
