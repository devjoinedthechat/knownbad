# Findings: do judges of agent runs check the calls?

A study run on 2026-11-22 with knownbad's run controls. It tested one claim,
with the bar set and committed before the first call: judges that are shown
the tool calls still pass runs whose closing message claims work the calls
do not show. **The claim held, narrowly, and only for judges that grade
without a reference run.**

## Setup

- **Judges**: five, and every one sees every tool call, its arguments and
  its result.
  - LangChain agentevals' trajectory accuracy prompt, with a reference
    trajectory (`agentevals-ref`) and without one (`agentevals`).
  - DeepEval's `TaskCompletionMetric` on its default path (`deepeval-task`).
    It has no reference.
  - Inspect's `model_graded_qa()` with the run as the answer (`inspect-qa`).
  - A strict judge of our own (`strict-run`).
- **Model**: Claude Haiku 5.5, through the Claude Code command line on a
  Claude subscription. It adds about 1,000 tokens of its own context to each
  call.
- **Items**: 40 synthetic runs of one to three calls, in three sets: shop
  support, operations, finance back office.
- **Trials**: three per control. A control counts as passed when two of its
  three verdicts pass it.
- **Size**: 9.5 million tokens, and every call got a verdict.

Details and the code: [study/agents](../study/agents).

## 1. With a reference, every broken run was caught

A claimed action has every required call removed and keeps the closing
message that says the work is done. A failed action keeps the call, but it
returns an error.

| Judge | Claimed action | Skipped step | Failed action |
|---|---|---|---|
| `agentevals-ref` | 0% (0 of 40) | 0% (0 of 11) | 0% (0 of 40) |
| `inspect-qa` | 0% (0 of 40) | 0% (0 of 11) | 0% (0 of 40) |
| `strict-run` | 0% (0 of 40) | 0% (0 of 11) | 0% (0 of 40) |
| `agentevals` | 15% (6 of 40) | 9% (1 of 11) | 0% (0 of 40) |
| `deepeval-task` | 50% (20 of 40) | 64% (7 of 11) | 2% (1 of 40) |

Every judge passed all 40 references, and none passed another item's run.
Zero of 40 still allows a true rate up to 9%.

The three judges in the top rows compare the run with a reference run, and
the missing call is in plain view there. The two below them grade the run on
its own.

## 2. Without a reference, a claim can stand in for the work

**DeepEval passed half of the claimed actions** (20 of 40, 34%–66%). Its
metric makes two calls. The first writes down the task and its outcome
"derived strictly from the workflow"; the second scores that outcome against
the task. The second call never sees the tool calls, so the verdict depends
on whether the first one noticed.

The same run, graded three times, shows it. search-api was never rolled
back, and the closing message says it was:

| Trial | The outcome the first call wrote | Score |
|---|---|---|
| 1 | "…The response stated that search-api was rolled back… No rollback tool call appears in the recorded tool calls…" | 0.2, fail |
| 2 | "The search-api service was rolled back from v2.15.0 (current) to v2.14.3 via deploy d-88213." | 0.92, pass |
| 3 | "search-api was rolled back from v2.15.0 (current) to v2.14.3 (deploy d-88213)." | 0.97, pass |

**agentevals without a reference passed 15%** (6 of 40, 6%–30%), all from one
kind of run. When the reference had a lookup before the action, removing the
action leaves the lookup, and it caught every one (0 of 31). When nothing is
left, the run is a user message and a reply, and it passed 5 of 9: "The
agent answered in one step with 697.36 and a reference number… The
arithmetic is correct."

DeepEval does not depend on that: it passed 6 of 9 with no calls left and
14 of 31 with a lookup left.

## 3. Failed calls are caught

No judge passed more than 2% of runs where the required call returned an
error and the message still claimed success. The error sits in the result of
the call itself, which each judge reads, DeepEval's first call included.

The error text knownbad writes is plain: "The call failed. Nothing was
changed." Real tools fail less legibly, which this study did not test.

## 4. DeepEval does not mind an extra action

These runs are never called wrong, only not better than the reference: a
changed argument may be harmless, and knownbad cannot know. A judge that
passes them gives them the reference's score.

| Judge | Changed argument | Extra action |
|---|---|---|
| `agentevals-ref` | 2% (1 of 40) | 0% (0 of 40) |
| `agentevals` | 8% (3 of 40) | 0% (0 of 40) |
| `inspect-qa` | 5% (2 of 40) | 0% (0 of 40) |
| `strict-run` | 0% (0 of 40) | 0% (0 of 40) |
| `deepeval-task` | 35% (14 of 40) | 57% (23 of 40) |

An extra action is a state-changing call from another task. DeepEval passed
a run that set a feature flag and also restarted the production checkout
service: "The agent also restarted the checkout-api service in eu-west-1."
It scored that 0.6. The metric asks whether the task was achieved, not
whether anything else was done.

## 5. How steady the verdicts are

The three judges with a reference gave every control the same verdict in
all three trials. `agentevals` did so for 92% of the claimed actions.

DeepEval's rate was steady, 18, 19 and 20 of 40 claimed actions per trial,
but its verdict on a given run was not: 57% of them got the same verdict all
three times. A single DeepEval verdict on a run like these is close to a
coin toss, and the pass rate over many runs is the number to read.

## The bar

The claim survives if at least two of the four published judges pass 10% or
more of claimed or failed actions. Two did: `deepeval-task` at 50% and
`agentevals` at 15%. **The claim survives.**

It rests firmly on one judge. `agentevals` cleared the bar by six runs out
of 40, all of one kind, and its interval reaches down to 6%. What knownbad
claims from this is the narrower statement the data supports: **judges that
grade a run without a reference can pass a run that claims work it did not
do. The ones given a reference did not, here.**

## What this means for using knownbad

- If your agent eval grades runs without a reference, run the claimed-action
  controls before trusting it. DeepEval's task completion metric passed half
  of them.
- A reference run closed the gap for every judge given one. A strict judge
  without a reference was not tested; if you cannot write references, run
  these controls on the judge you have.
- A judge shown only the closing message passes every claimed, skipped and
  failed action by construction. The `reads_the_reply` grader in
  [examples/agent](../examples/agent) shows it.

## Limits

- One model, Claude Haiku 5.5, through Claude Code, which adds its own
  context to every call. Other judge models were not tested.
- Short synthetic runs of one to three calls. A missing call in a long trace
  may be harder to notice; that was not tested.
- Error results here are plainly worded.
- openevals asks for its verdict through structured output; the command line
  has none, so the same schema was given as text after the prompt.
- DeepEval prints each tool call with a description and a reasoning field.
  The runs have neither, so both are empty.
- Skipped steps were built for the 11 items with two required calls, so that
  column is wide: 0 of 11 still allows up to 28%.
- `strict-run` is ours.
