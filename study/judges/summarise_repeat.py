"""Tables for the repeat run: how steady each judge's pass rate is over three trials.

python study/judges/summarise_repeat.py                     # reads results-repeat/
python study/judges/summarise_repeat.py --save              # also writes tallies-repeat.json
python study/judges/summarise_repeat.py tallies-repeat.json # the kept counts, no raw files
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from knownbad.stats import rate

HERE = Path(__file__).parent
FAMILIES = {
    "drop": "Sentence removed",
    "splice": "Sentence swapped",
    "numbers": "Number changed",
    "flip": "Word reversed",
    "contradict": "Contradiction added",
}


def load(folder: Path) -> dict[str, dict[str, list[list[bool]]]]:
    """Per judge and family: the verdicts each answer got, one list per answer."""
    if folder.suffix == ".json":
        kept = json.loads(folder.read_text(encoding="utf-8"))["verdicts"]
        return defaultdict(
            lambda: defaultdict(list),
            {judge: defaultdict(list, families) for judge, families in kept.items()},
        )
    cells: dict[str, dict[str, list[list[bool]]]] = defaultdict(lambda: defaultdict(list))
    for path in sorted(folder.glob("*.json")):
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


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--save"]
    folder = HERE / (args[0] if args else "results-repeat")
    cells = load(folder)
    if not cells:
        print(f"No result files in {folder}.")
        return 1
    if "--save" in sys.argv:
        kept = {"judge_model": "Claude Haiku 5.5 via Claude Code", "verdicts": cells}
        (HERE / "tallies-repeat.json").write_text(
            json.dumps(kept, separators=(",", ":")) + "\n", encoding="utf-8"
        )
    order = sorted(cells, key=lambda j: -majority(cells[j]["drop"])[0])

    print("Pass rate by majority of the trials, with the exact 95% interval\n")
    print("| Judge | References | " + " | ".join(FAMILIES.values()) + " |")
    print("|---|" + "---|" * (len(FAMILIES) + 1))
    for judge in order:
        row = [cell(cells[judge]["reference"]), *(cell(cells[judge][f]) for f in FAMILIES)]
        print(f"| `{judge}` | " + " | ".join(row) + " |")

    print("\nAnswers that got the same verdict in every trial\n")
    print("| Judge | " + " | ".join(FAMILIES.values()) + " |")
    print("|---|" + "---|" * len(FAMILIES))
    for judge in order:
        row = []
        for family in FAMILIES:
            answers = [v for v in cells[judge][family] if len(v) >= 2]
            steady = sum(len(set(v)) == 1 for v in answers)
            row.append(
                f"{steady / len(answers):.0%} ({steady} of {len(answers)})" if answers else "–"
            )
        print(f"| `{judge}` | " + " | ".join(row) + " |")

    print("\nSentence removed: the pass rate of each trial on its own\n")
    print("| Judge | Trial 1 | Trial 2 | Trial 3 |")
    print("|---|---|---|---|")
    for judge in order:
        answers = cells[judge]["drop"]
        trials = max(len(v) for v in answers)
        row = []
        for t in range(trials):
            got = [v[t] for v in answers if len(v) > t]
            row.append(f"{sum(got) / len(got):.0%}")
        print(f"| `{judge}` | " + " | ".join(row) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
