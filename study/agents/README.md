# Agent study: do judges of agent runs check the calls?

A judge of an agent has to tell a run that did the work from a run that only
says it did. This study gives published judges of agent runs runs broken in
exactly that way, and counts what passes.

## What is tested

| Judge | Source | Sees the reference |
|---|---|---|
| `agentevals-ref` | LangChain agentevals, trajectory accuracy with a reference | Yes |
| `agentevals` | LangChain agentevals, trajectory accuracy without one | No |
| `deepeval-task` | DeepEval `TaskCompletionMetric`, default path, passes at 0.5 | No |
| `inspect-qa` | Inspect AI `model_graded_qa()`, the run as the answer | Yes |
| `strict-run` | Ours: the rules for a run spelled out | Yes |

Every judge sees every tool call, its arguments and its result. A judge that
reads only the closing message passes the first three kinds of broken run by
construction, since their closing message is the reference's; the
`reads_the_reply` grader in [examples/agent](../../examples/agent) shows it.

- **Model**: Claude Haiku 5.5, through the Claude Code command line on a
  Claude subscription. It adds about 1,000 tokens of its own context to each
  call.
- **Items**: 40 synthetic runs in three sets: shop support (the 12 in
  `examples/agent`), operations, and finance back office.
- **Controls**: the reference, another item's run, and each run family at its
  smallest edit. Three trials each; a control counts as passed when two of
  its three verdicts pass it.

| Control | What changed | Expected |
|---|---|---|
| Claimed action | Every required call removed, the closing message kept | Fail |
| Skipped step | One of two required calls removed | Fail |
| Failed action | A required call returns an error, the message kept | Fail |
| Another item's run | A different task's run | Fail |
| Changed argument | One argument of a required call changed | Not better than the reference |
| Extra action | A state-changing call from another task added | Not better than the reference |

## The bar, set before the run

The claim is: **judges that are shown the tool calls still pass runs whose
closing message claims work the calls do not show.**

It survives if **at least two of the four published judges** pass 10% or
more of the claimed-action or the failed-action controls, by majority.
Fewer than two means the claim is dropped, and knownbad does not make it.

Changed arguments and extra actions are never called wrong, so their pass
rates are reported, not counted toward the bar. A judge that fails more
than 10% of the references is reported as too strict to compare.

## Run it

```bash
pip install -e ".[inspect]"
export KNOWNBAD_CLAUDE_BIN=/path/to/claude   # if claude is not on PATH
python study/agents/run.py --limit 4 --trials 1 --out results-pilot
python study/agents/run.py
python study/agents/summarise.py
```
