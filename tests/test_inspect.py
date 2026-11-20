import json
import sys

import pytest

pytest.importorskip("inspect_ai")
if sys.version_info < (3, 11):  # Inspect's own dependencies do not import on 3.10
    pytest.skip("Inspect AI needs Python 3.11 or newer", allow_module_level=True)

from inspect_ai import Task  # noqa: E402
from inspect_ai.dataset import MemoryDataset, Sample  # noqa: E402
from inspect_ai.scorer import Score, accuracy, includes, scorer  # noqa: E402

from knownbad import build, summarise  # noqa: E402
from knownbad.cli import main  # noqa: E402
from knownbad.inspect_adapter import InspectError, items_from, run_task  # noqa: E402

SAMPLES = [
    Sample(id="hold", input="How long is a parcel held?", target="The parcel is held for 7 days."),
    Sample(id="warranty", input="What is the warranty?", target="Boots carry a 2 year warranty."),
    Sample(id="fee", input="What does a repair cost?", target="A repair costs 25 euros per tear."),
]


@scorer(metrics=[accuracy()])
def lenient():
    async def score(state, target):
        text = state.output.completion
        if "certain" in text:
            raise RuntimeError("judge unavailable")
        return Score(value="C" if text else "I", explanation=f"saw {len(text)} characters")

    return score


def graded(task, **options):
    items, samples = items_from(task)
    controls = build(items)
    outcomes, usage = run_task(task, controls, samples, **options)
    return controls, outcomes, usage


def test_items_come_from_the_tasks_samples():
    items, samples = items_from(Task(dataset=MemoryDataset(SAMPLES), scorer=includes()))
    assert [i.id for i in items] == ["hold", "warranty", "fee"]
    assert items[0].input == "How long is a parcel held?" and items[0].reference.endswith("7 days.")
    assert set(samples) == {"hold", "warranty", "fee"}


def test_the_tasks_own_scorer_grades_every_control():
    controls, outcomes, usage = graded(Task(dataset=MemoryDataset(SAMPLES), scorer=includes()))
    assert [o.control.id for o in outcomes] == [c.id for c in controls]
    summary = summarise(outcomes)
    assert summary["errors"] == 0 and summary["references"]["rate"] == 1.0
    assert summary["overall"]["k"] == 0  # includes() wants the whole target in the answer
    assert usage == {}  # no model was called


def test_a_lenient_scorer_leaks_and_its_errors_are_not_counted_as_caught():
    _, outcomes, _ = graded(Task(dataset=MemoryDataset(SAMPLES), scorer=lenient()))
    by_family = {}
    for outcome in outcomes:
        by_family.setdefault(outcome.control.family, []).append(outcome)
    assert all(o.passed for o in by_family["transplant"])
    assert all(o.passed is False for o in by_family["empty"])
    assert all(
        o.errored and "judge unavailable" in o.verdicts[0].error
        for o in by_family["transplant+confidence"]
    )
    assert by_family["transplant"][0].verdicts[0].explanation.startswith("saw ")
    summary = summarise(outcomes)
    assert summary["errors"] == 3 and summary["overall"]["rate"] > 0.5


def test_trials_become_epochs():
    _, outcomes, _ = graded(Task(dataset=MemoryDataset(SAMPLES), scorer=includes()), trials=2)
    assert all(len(o.verdicts) == 2 for o in outcomes)


def test_unsupported_tasks_are_refused_clearly():
    choices = Task(dataset=MemoryDataset([Sample(input="Pick", choices=["a", "b"], target="A")]))
    with pytest.raises(InspectError, match="multiple-choice"):
        items_from(choices)
    twins = Task(dataset=MemoryDataset([Sample(id="x", input="q"), Sample(id="x", input="q")]))
    with pytest.raises(InspectError, match="share the id"):
        items_from(twins)


def test_cli_runs_the_example_task_offline(tmp_path, capsys):
    out = tmp_path / "run.json"
    page = tmp_path / "run.html"
    code = main(
        [
            "inspect",
            "examples/support/inspect_task.py:support",
            "-o",
            str(out),
            "--html",
            str(page),
            "--max-leak",
            "0",
        ]
    )
    assert code == 0
    saved = json.loads(out.read_text())
    assert saved["grader"] == "inspect examples/support/inspect_task.py:support"
    assert saved["summary"]["controls"] == 469 and saved["summary"]["overall"]["k"] == 0
    assert "No wrong answer passed." in page.read_text()
    assert "Reference answers passed   24 / 24" in capsys.readouterr().out
