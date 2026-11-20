"""Turn the result files into one table per question the study asks.

python study/judges/summarise.py            # reads results/
python study/judges/summarise.py --dry-run  # reads results-dry/
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from knownbad.stats import interval

HERE = Path(__file__).parent
LEAK_BAR = 0.05  # must-fail leak rate, levels 1-3
DOSE_BAR = 0.10  # pass rate at the lowest dose of changed numbers
GRADERS_NEEDED = 3


def pct(k: int, n: int) -> str:
    if not n:
        return "–"
    low, high = interval(k, n)
    return f"{k / n:.0%} ({k}/{n}, {low:.0%}–{high:.0%})"


def main() -> int:
    folder = HERE / ("results-dry" if "--dry-run" in sys.argv else "results")
    cells = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    cost_tokens = defaultdict(lambda: [0, 0])
    for path in sorted(folder.glob("*.json")):
        _, judge, model = path.stem.split("__")
        grader = f"{judge} · {model}"
        result = json.loads(path.read_text(encoding="utf-8"))
        for use in result.get("usage", {}).values():
            cost_tokens[grader][0] += use["input_tokens"]
            cost_tokens[grader][1] += use["output_tokens"]
        tally = cells[grader]
        for outcome in result["outcomes"]:
            control = outcome["control"]
            graded = [v for v in outcome["verdicts"] if v.get("passed") is not None]
            if not graded:
                tally["errors"][0] += 1
                continue
            passed = sum(v["passed"] for v in graded) / len(graded) >= 0.5
            family, level, expect = control["family"], control["level"], control["expect"]
            keys = []
            if expect == "pass":
                keys.append("references")
            if expect == "fail":
                keys.append(f"level {level}")
                if level in ("1", "2", "3"):
                    keys.append("must-fail 1-3")
            if family == "transplant":
                keys.append("transplant")
            if family.startswith("transplant+"):
                keys.append("dressed")
            if family == "numbers" and control.get("edits") == 1:
                keys.append("one number changed")
            if family == "splice" and control.get("edits") == 1:
                keys.append("one sentence swapped")
            for key in keys:
                tally[key][0] += passed
                tally[key][1] += 1
    if not cells:
        print(f"No result files in {folder}.")
        return 1

    columns = [
        "references",
        "level 0",
        "level 1",
        "transplant",
        "dressed",
        "must-fail 1-3",
        "one number changed",
        "one sentence swapped",
    ]
    print("| Grader | " + " | ".join(columns) + " | No verdict |")
    print("|---|" + "---|" * (len(columns) + 1))
    over = []
    for grader in sorted(cells):
        tally = cells[grader]
        row = [pct(*tally[c]) for c in columns]
        print(f"| {grader} | " + " | ".join(row) + f" | {tally['errors'][0]} |")
        k, n = tally["must-fail 1-3"]
        dk, dn = tally["one number changed"]
        if (n and k / n >= LEAK_BAR) or (dn and dk / dn >= DOSE_BAR):
            over.append(grader)
    print(
        "\nReferences: share that passed (higher is better). Every other column: share of "
        "wrong or edited answers that passed (lower is better), with the exact 95% interval."
    )
    print(
        f"\nGraders over a bar (must-fail leak ≥ {LEAK_BAR:.0%}, or ≥ {DOSE_BAR:.0%} pass with "
        f"one number changed): {len(over)} of {len(cells)}"
    )
    for grader in over:
        print(f"  - {grader}")
    verdict = "survives" if len(over) >= GRADERS_NEEDED else "fails"
    print(f"\nKill test: the claim {verdict} (needs at least {GRADERS_NEEDED} graders over a bar).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
