# Contributing

## Set up

```bash
uv venv -p 3.12 && uv pip install -e ".[inspect]" --group dev
.venv/bin/pytest --cov && .venv/bin/mypy && .venv/bin/ruff check . && .venv/bin/ruff format --check .
```

All four must pass. Coverage has a floor of 90%.

## Rules for a new control

A control is only useful if its verdict is known before the grader sees it.

1. **No model writes or labels it.** A builder is a plain function of the
   items and a seed.
2. **State the claim it can defend.** `fail` only when the answer is wrong for
   any reasonable rubric. If an edit might be harmless, use `not_higher`
   against the less-edited answer.
3. **Say how it was built** in the `how` field, in one sentence a reader of
   the report can check against the answer.
4. **Guard it.** Drop the control where the construction would produce a
   right answer, and add a test for that case.
5. **Keep it deterministic.** The same items and seed must give the same
   bytes. `tests/test_properties.py` checks the shared invariants for random
   items; extend it when a new family adds one.

## Changes to numbers

Anything that changes a reported rate, interval or threshold needs a test
with a value worked out by hand or taken from a published table.

## Commits

One change per commit, with a message that says what a user can now do or
what was wrong.
