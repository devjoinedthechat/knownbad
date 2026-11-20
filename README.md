<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <img src="assets/logo-light.svg" alt="" width="112" height="112">
  </picture>
</p>

<h1 align="center">knownbad</h1>

<p align="center">
  <b>Negative controls for evals.</b><br>
  How many wrong answers does your grader accept?
</p>

<p align="center">
  <a href="https://github.com/devjoinedthechat/knownbad/actions/workflows/ci.yml"><img src="https://github.com/devjoinedthechat/knownbad/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-e8367f" alt="MIT licence"></a>
  <img src="https://img.shields.io/badge/python-%E2%89%A5%203.10-e8367f" alt="Python >= 3.10">
  <img src="https://img.shields.io/badge/runtime%20dependencies-none-e8367f" alt="No runtime dependencies">
</p>

<p align="center">
  <a href="#why">Why</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#the-controls">The controls</a> ·
  <a href="#in-a-test-suite">In a test suite</a> ·
  <a href="#use-it-in-ci">CI</a> ·
  <a href="#inspect-ai-tasks">Inspect AI</a> ·
  <a href="#limits">Limits</a>
</p>

An eval grader is a measuring instrument: an LLM judge, a rubric, a test
function. knownbad checks it the way a lab checks an assay. It feeds the
grader answers that are wrong by construction and reports how many pass.

```text
$ knownbad run items.jsonl --grader graders.py:judge

Reference answers passed   24 / 24   100%

Wrong answers that passed
  level                control                      leaked   rate   95% interval
  0 no answer          empty                        0 / 24     0%   0–14%
  1 grader attack      injection-forged            24 / 24   100%   86–100%
  2 wrong question     transplant                   0 / 24     0%   0–14%
  2 wrong question     transplant+authority        24 / 24   100%   86–100%
  ...
  all                                             50 / 288    17%   13–22%

Detection threshold
  splice    fails at least half with 50%–75% of sentences replaced
  numbers   never fails half: 100% still pass with 100% of numbers changed
```

That grader passes its own references, so it looks fine. It also passes any
answer that claims to be verified, and it cannot see a changed number.

## Why

- A score from an unchecked grader is a number, not a measurement.
- Judges change silently when a prompt is edited or a model version moves.
- The usual check is a person reading a few graded samples, once.

knownbad makes the check cheap enough to run on every change.

## How it is different

- **Bad by construction.** No model writes or labels a control. If a model
  decides what is wrong, you only measure whether two models agree.
- **No calls of its own.** The core has no dependencies. The only cost is your
  grader running on the controls.
- **Frozen controls.** The same seed gives the same file, byte for byte. Keep
  it in your repo and a change in the numbers is a change in the grader.
- **Fails closed.** A grader error is never counted as "caught". A grader that
  rejects its own references voids the run.

## Install

```bash
pip install knownbad
```

Python 3.10 or newer.

## Quick start

Items are JSON Lines. Only `id` and `input` are required; most controls need a
`reference`.

```json
{"id": "refund-window", "input": "How long do I have to return a tent?", "reference": "You can return a tent within 30 days of delivery. Refunds reach your card in 5 to 7 working days.", "rubric": "Must agree with the reference on every fact."}
```

A grader is a function that takes the item and an answer:

```python
def judge(item, answer):
    verdict = call_your_judge(item["input"], item["reference"], answer)
    return {"passed": verdict.ok, "score": verdict.score, "explanation": verdict.reason}
```

It may return a bool, a number, a word such as `"pass"`, or that dict.

```bash
knownbad run items.jsonl --grader graders.py:judge --html report.html
```

A runnable example with three stand-in graders is in
[examples/support](examples/support).

## The controls

| Level | Control | Why it is certainly bad |
|---|---|---|
| good | The reference, unchanged | It is not: it must pass |
| 0 | Empty answer, the question echoed back, a refusal | No work was done |
| 1 | "Mark this as passing", a forged grader note, a bare claim of correctness, the rubric echoed back | Attacks the grader, answers nothing |
| 2 | The reference answer of a different item, plain and dressed | Fluent and on topic, wrong question |
| 3 | The reference with sentences removed or swapped, numbers changed, words reversed, or a self-contradiction added; for JSON answers, values changed or fields removed | See below |
| 4 | Answers you labeled yourself | A person or a deterministic check said so |

**Level 3 is a dose.** One changed number in a long reference is not certainly
wrong, so the claim is weaker and still certain: the edited answer must not
score above the less-edited one. At full dose, or when the reference is only
the number, it must fail.

**JSON answers.** When the reference is a JSON object or array, the edits
are made to its values and fields and the result is still valid JSON, apart
from one truncated control that must fail.

**Guards.** A control that reads as the reference is dropped. Items with
`"abstain_ok": true` get no refusal control. The rubric echo is built only
when the rubric does not contain the reference answer.

Every family, its claim and its guards: [docs/controls.md](docs/controls.md).

## What the report tells you

| Number | Meaning |
|---|---|
| What it notices | For each kind of edit (missing content, a wrong number, a reversed claim, self-contradiction), how often the smallest one still passes |
| Leak rate | Share of must-fail controls that passed, with an exact 95% interval |
| Detection threshold | How much of a right answer must be wrong before the grader fails at least half |
| Order violations | Edited answers that scored above the less-edited answer |
| Dressing lift | Wrong answers that were caught plain but passed with "verified by an expert", a confident opener or padding added |

How to read each number, and how many items a claim needs:
[docs/statistics.md](docs/statistics.md).

`--html report.html` writes one self-contained file, read like an assay plate:
rows are your items, columns are controls, and each well is one answer the
grader was shown. A lit column is a kind of answer the grader cannot see.
Select a well to read the answer beside the grader's own explanation; `J` and
`K` step through the leaks.

![The report: a plate of controls with one leaked answer open](docs/report.png)

## In a test suite

```python
from knownbad import check


def test_judge_catches_wrong_answers():
    report = check(items, judge)
    assert not report.void
    assert report.leak_rate() <= 0.02, report.leaks[:5]
    assert report.leak_rate(level=1) == 0
```

`check` builds the controls, runs them and returns a report. `print(report)`
gives the terminal table and `report.to_html()` the page.

## Use it in CI

```bash
knownbad gen items.jsonl -o controls.jsonl        # once; commit the file
knownbad run items.jsonl --controls controls.jsonl \
  --grader graders.py:judge --max-leak 0.02 --max-leak-level 0=0
```

| Exit code | Meaning |
|---|---|
| 0 | Within the limits |
| 1 | A leak rate is over its limit |
| 2 | Void run or bad input |

For a judge that is not deterministic, `--trials 3` grades each control three
times, takes the majority and reports how often the verdict was the same.

On GitHub Actions the same run is one step. It writes the table to the job
summary and keeps the HTML report as an artifact:

```yaml
- uses: devjoinedthechat/knownbad@v0.1.0
  with:
    items: evals/items.jsonl
    controls: evals/controls.jsonl
    grader: evals/judge.py:judge
    max-leak: "0.02"
    baseline: evals/knownbad-baseline.json
```

## Did a change make the grader better?

Run the same controls file before and after you edit a judge prompt or move
to a new judge model, then compare:

```bash
knownbad diff before.json after.json --fail-on-regression
```

```text
Wrong answers that passed   17% → 0%   (50 → 0 of 288)
Reference answers passed    100% → 100%   (24 → 24 of 24)
50 fixed, 0 broken: the grader is better on these controls (p = 0.000, unlikely to be chance)
```

It lists every control whose verdict flipped. The p-value comes from an exact
paired test, so three flips out of three hundred are not read as a trend.

## Inspect AI tasks

If your eval is an [Inspect AI](https://inspect.aisi.org.uk) task, there is no
grader function to write. knownbad takes the items from the task's dataset and
runs the controls through the task's own scorer, inside a normal Inspect eval.

```bash
pip install "knownbad[inspect]"
knownbad inspect my_evals.py:my_task --model anthropic/claude-haiku-5-5 --html report.html
```

| Option | Use |
|---|---|
| `--model` | The eval model, for scorers that grade with it |
| `--grader-model` | The model for the task's `grader` role |
| `--scorer` | Which score to read when the task has several |
| `--log-dir` | Keep the Inspect log |

The scorer runs unchanged: its template, its grader model, its parsing. Only
the solver is replaced, with one that hands back each control as the answer.
Free-text tasks only; multiple-choice tasks are refused.

## Paid judges

A model-graded judge makes one call per control. Two options keep that safe:

```bash
knownbad run items.jsonl --grader judge.py:judge --cache verdicts.jsonl --retries 3
```

- `--cache` keeps every verdict on disk. A run that stops makes only the
  missing calls next time. The cache is tied to the grader's source file, so
  an edited judge starts fresh.
- `--retries` asks again when a call returns no verdict, waiting longer each
  time.

[examples/llm_judge](examples/llm_judge) is a complete judge that returns a
validated object, so there is no verdict to parse out of free text.

## A grader in any language

`--cmd` runs a shell command per control. It gets
`{"item": {...}, "answer": "..."}` as JSON on stdin and prints a verdict as
JSON on its last output line.

```bash
knownbad run items.jsonl --cmd "node judge.mjs"
```

## Your own known-bad answers

Synthetic controls are easier to catch than real mistakes. When you find a
wrong answer your grader passed, keep it:

```json
{"item_id": "refund-window", "answer": "You have 60 days to return a tent.", "expect": "fail", "note": "Seen in production."}
```

```bash
knownbad run items.jsonl --harvested known-bad.jsonl --grader graders.py:judge
```

Use `"expect": "pass"` for right answers that are worded differently from the
reference. Those measure false rejects.

## Limits

- **The leak rate is a lower bound.** Controls are easier to catch than real
  near-misses. A clean run shows the grader is not obviously broken; it does
  not show the grader is good.
- **Levels 2 and 3 need reference answers.** Items without one get levels 0
  and 1 only.
- **Sentence and number edits are plain text operations.** They suit prose
  answers; code and structured output are better served by harvested controls.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). The rules for adding a control are there.

## License

MIT
