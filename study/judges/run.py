"""Run knownbad's controls against published judge prompts, under a spend cap.

    python study/judges/run.py --dry-run          # offline: checks the whole pipeline
    python study/judges/run.py --cap 10           # needs ANTHROPIC_API_KEY

Each cell is one judge prompt, one judge model and one item set. A finished
cell is a normal knownbad result file in results/, so a stopped run resumes
where it left off and every cell opens with `knownbad report`.

The cap is enforced from measured token use: before a cell runs, its cost is
projected from the cells already done on the same model, and a cell that
would cross the cap is skipped and listed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from inspect_ai import Task  # noqa: E402
from inspect_ai.dataset import MemoryDataset, Sample  # noqa: E402
from inspect_ai.scorer import includes  # noqa: E402
from judges import JUDGES  # noqa: E402

from knownbad import build  # noqa: E402
from knownbad.cli import make_result  # noqa: E402
from knownbad.inspect_adapter import items_from, run_task  # noqa: E402
from knownbad.io import read_jsonl, write_json  # noqa: E402

SETS = {
    "support": HERE.parent.parent / "examples" / "support" / "items.jsonl",
    "facts": HERE / "sets" / "facts.jsonl",
    "runbooks": HERE / "sets" / "runbooks.jsonl",
}
# Dollars per million tokens: (input, output). Checked 2026-11-20.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "lfm-3-1.7b": (0.08, 0.20),
    "llama-3.2-3b-instruct": (0.05, 0.33),
    "gemma-3-4b-it": (0.05, 0.10),
    "llama-3.1-8b-instruct": (0.02, 0.04),
    "ministral-8b-2512": (0.15, 0.15),
}
# Each plan: (Inspect model id, judges, every nth item).
PLANS = {
    # The larger model costs about twenty times more per token, so it grades
    # three judges on every third item.
    "claude": (
        ("anthropic/claude-haiku-5-5", tuple(JUDGES), 1),
        ("anthropic/claude-sonnet-5-5", ("inspect-qa", "inspect-fact", "naive"), 3),
    ),
    # Small open models, hosted. Three judges on every second item: the
    # question is whether a small judge passes plainly wrong answers at all.
    "small": tuple(
        (f"openrouter/{name}", ("inspect-qa", "langchain-qa", "strict"), 2)
        for name in (
            "liquid/lfm-3-1.7b",
            "meta-llama/llama-3.2-3b-instruct",
            "google/gemma-3-4b-it",
            "meta-llama/llama-3.1-8b-instruct",
            "mistralai/ministral-8b-2512",
        )
    ),
}
# Before a model's cost is measured, assume this much per control. Deliberately high.
FIRST_GUESS = 0.012


def cost_of(usage: dict[str, dict[str, int]]) -> float:
    total = 0.0
    for name, use in usage.items():
        price = next((p for model, p in PRICES.items() if model in name), None)
        if price is None:
            continue
        # Reasoning tokens are added on top of output tokens. If the provider
        # already counts them there this overstates the cost, which is the safe side.
        out = use["output_tokens"] + use.get("reasoning_tokens", 0)
        total += use["input_tokens"] / 1e6 * price[0] + out / 1e6 * price[1]
    return total


def task_for(set_name: str, judge: str, nth: int, dry_run: bool) -> Task:
    rows = read_jsonl(SETS[set_name])[::nth]
    samples = [Sample(id=r["id"], input=r["input"], target=r["reference"]) for r in rows]
    scorer = includes() if dry_run else JUDGES[judge]()
    return Task(dataset=MemoryDataset(samples), scorer=scorer)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--cap", type=float, default=10.0, help="stop before spending more, in dollars"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="no model calls; writes to results-dry/"
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--only", help="run only cells whose name contains this text")
    parser.add_argument("--plan", choices=sorted(PLANS), default="claude")
    args = parser.parse_args()

    folder = "results" if args.plan == "claude" else f"results-{args.plan}"
    out_dir = HERE / ("results-dry" if args.dry_run else folder)
    out_dir.mkdir(exist_ok=True)
    spent = 0.0
    per_control: dict[str, list[float]] = {}
    skipped: list[str] = []

    # Money already spent by finished cells counts toward the cap on a resume.
    for path in sorted(out_dir.glob("*.json")):
        done = json.loads(path.read_text(encoding="utf-8"))
        cell_cost = cost_of(done.get("usage", {}))
        spent += cell_cost
        model = path.stem.split("__")[2]
        if done["summary"]["controls"]:
            per_control.setdefault(model, []).append(cell_cost / done["summary"]["controls"])

    for model_id, judges, nth in PLANS[args.plan]:
        model = model_id.rsplit("/", 1)[-1]
        for judge in judges:
            for set_name in SETS:
                name = f"{set_name}__{judge}__{model}"
                path = out_dir / f"{name}.json"
                if args.only and args.only not in name:
                    continue
                if path.exists():
                    print(f"done     {name}")
                    continue
                task = task_for(set_name, judge, nth, args.dry_run)
                items, samples = items_from(task)
                controls = build(items)
                seen = per_control.get(model)
                rate = max(seen) if seen else FIRST_GUESS
                projected = 0.0 if args.dry_run else rate * len(controls)
                if spent + projected > args.cap:
                    skipped.append(f"{name} (about ${projected:.2f}, ${args.cap - spent:.2f} left)")
                    continue
                outcomes, usage = run_task(
                    task,
                    controls,
                    samples,
                    model="mockllm/model" if args.dry_run else model_id,
                    max_connections=args.workers,
                )
                result = make_result(
                    outcomes, {i.id: i for i in items}, f"{judge} · {model}", 1, usage
                )
                write_json(path, result)
                cell_cost = cost_of(usage)
                spent += cell_cost
                if not args.dry_run:
                    per_control.setdefault(model, []).append(cell_cost / len(controls))
                summary = result["summary"]
                print(
                    f"ran      {name}: {summary['overall']['k']}/{summary['overall']['n']} leaked, "
                    f"{summary['errors']} errors, ${cell_cost:.3f} (total ${spent:.2f})"
                )
    for line in skipped:
        print(f"skipped  {line}")
    print(
        f"\nSpent ${spent:.2f} of ${args.cap:.2f}. Results in {out_dir.relative_to(HERE.parent.parent)}/"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
