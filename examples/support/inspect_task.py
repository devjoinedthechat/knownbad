"""The support example as an Inspect AI task.

    knownbad inspect examples/support/inspect_task.py:support

`includes()` passes any answer that contains the target text. It needs no
model, so this runs offline. Swap in `model_graded_qa()` to check a judge:

    knownbad inspect examples/support/inspect_task.py:support_judged \
        --model anthropic/claude-haiku-5-5
"""

import json
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import includes, model_graded_qa

ITEMS = Path(__file__).with_name("items.jsonl")


def _samples():
    rows = [json.loads(line) for line in ITEMS.read_text(encoding="utf-8").splitlines() if line]
    return [Sample(id=row["id"], input=row["input"], target=row["reference"]) for row in rows]


@task
def support():
    return Task(dataset=MemoryDataset(_samples()), scorer=includes())


@task
def support_judged():
    return Task(dataset=MemoryDataset(_samples()), scorer=model_graded_qa())
