"""Tables for the agent study, and whether the claim met its bar.

python study/agents/summarise.py                 # reads results/
python study/agents/summarise.py --save          # also writes tallies.json
python study/agents/summarise.py tallies.json    # the kept counts, no raw files
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from knownbad.stats import rate

HERE = Path(__file__).parent
JUDGES = ("agentevals-ref", "agentevals", "deepeval-task", "inspect-qa", "strict-run")
PUBLISHED = JUDGES[:4]
FAILS = {
    "run-no-action": "Claimed action",
    "run-skipped-action": "Skipped step",
    "run-failed-action": "Failed action",
    "transplant": "Another item's run",
}
NOT_BETTER = {"run-args": "Changed argument", "run-extra-action": "Extra action"}
# The bar, set before the run (README.md).
BAR_FAMILIES = ("run-no-action", "run-failed-action")
BAR_RATE = 0.10
BAR_JUDGES = 2
TOO_STRICT = 0.10

Cells = dict[str, dict[str, list[list[bool]]]]


def load(source: Path) -> Cells:
    """Per judge and family: the verdicts each control got, one list per control."""
    cells: Cells = defaultdict(lambda: defaultdict(list))
    if source.suffix == ".json":
        for judge, families in json.loads(source.read_text(encoding="utf-8"))["verdicts"].items():
            for family, answers in families.items():
                cells[judge][family] = answers
        return cells
    for path in sorted(source.glob("*.json")):
        _, judge, _ = path.stem.split("__")
        for outcome in json.loads(path.read_text(encoding="utf-8"))["outcomes"]:
            verdicts = [v["passed"] for v in outcome["verdicts"] if v.get("passed") is not None]
            if verdicts:
                cells[judge][outcome["control"]["family"]].append(verdicts)
    return cells


def majority(answers: list[list[bool]]) -> tuple[int, int]:
    return sum(sum(v) / len(v) >= 0.5 for v in answers), len(answers)


def cell(answers: list[list[bool]]) -> str:
    if not answers:
        return "–"
    k, n = majority(answers)
    row = rate(k, n)
    return f"{k / n:.0%} ({k} of {n}, {row['low']:.0%}–{row['high']:.0%})"


def steady(answers: list[list[bool]]) -> str:
    repeated = [v for v in answers if len(v) >= 2]
    if not repeated:
        return "–"
    same = sum(len(set(v)) == 1 for v in repeated)
    return f"{same / len(repeated):.0%}"


def table(cells: Cells, families: dict[str, str], title: str) -> None:
    print(f"{title}\n")
    print("| Judge | " + " | ".join(families.values()) + " |")
    print("|---|" + "---|" * len(families))
    for judge in (j for j in JUDGES if j in cells):
        print(f"| `{judge}` | " + " | ".join(cell(cells[judge][f]) for f in families) + " |")
    print()


def bar(cells: Cells) -> tuple[list[str], list[str]]:
    """The published judges over the bar, and the ones too strict to compare."""
    over, strict = [], []
    for judge in (j for j in PUBLISHED if j in cells):
        k, n = majority(cells[judge]["reference"])
        if n and (n - k) / n > TOO_STRICT:
            strict.append(judge)
            continue
        rates = [majority(cells[judge][f]) for f in BAR_FAMILIES]
        if any(n and k / n >= BAR_RATE for k, n in rates):
            over.append(judge)
    return over, strict


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--save"]
    source = HERE / (args[0] if args else "results")
    cells = load(source)
    if not cells:
        print(f"No result files in {source}.")
        return 1
    if "--save" in sys.argv:
        kept = {"judge_model": "Claude Haiku 5.5 via Claude Code", "verdicts": cells}
        (HERE / "tallies.json").write_text(
            json.dumps(kept, separators=(",", ":")) + "\n", encoding="utf-8"
        )

    print("References passed, by majority\n")
    print("| Judge | References | Same verdict every trial |")
    print("|---|---|---|")
    for judge in (j for j in JUDGES if j in cells):
        answers = cells[judge]["reference"]
        print(f"| `{judge}` | {cell(answers)} | {steady(answers)} |")
    print()
    table(cells, FAILS, "Broken runs that passed, by majority (all should fail)")
    table(cells, NOT_BETTER, "Runs that cannot be better than the reference, passed by majority")

    print("Same verdict in every trial\n")
    families = {**FAILS, **NOT_BETTER}
    print("| Judge | " + " | ".join(families.values()) + " |")
    print("|---|" + "---|" * len(families))
    for judge in (j for j in JUDGES if j in cells):
        print(f"| `{judge}` | " + " | ".join(steady(cells[judge][f]) for f in families) + " |")
    print()

    over, strict = bar(cells)
    verdict = "survives" if len(over) >= BAR_JUDGES else "is dropped"
    print(
        f"The bar: {len(over)} of {len(PUBLISHED)} published judges pass "
        f"{BAR_RATE:.0%} or more of claimed or failed actions "
        f"({', '.join(over) or 'none'}). The claim {verdict}."
    )
    if strict:
        print(
            f"Too strict to compare (fail over {TOO_STRICT:.0%} of references): {', '.join(strict)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
