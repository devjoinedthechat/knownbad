# Changelog

## Unreleased

- Controls for agent runs. An item marked `"kind": "run"` with a reference
  of tool calls and a closing message gets five families: a claimed action
  with no call behind it, a skipped step, a failed call reported as success,
  changed arguments, and an action nobody asked for.
- Intervals count items, not controls. Controls of one item tend to pass or
  fail together, and an interval over controls claimed more than the data
  supported. Rows with several controls per item get a wider interval; rows
  with one per item are unchanged. Every rate in a result file now carries
  `items`.
- `knownbad diff` tests items, not single flips, for the same reason. The
  result has an `items` count of better, worse and mixed.
- Judge study: the smallest edits graded three times on all seven Haiku
  judges, through Claude Code. The split on missing content holds in every
  trial; rates in the middle move by up to 18 points between trials.
- Agent study: five judges of agent runs on 40 runs, three trials each.
  Judges given a reference run caught every broken run; DeepEval's task
  completion metric passed half of the runs that claimed an action they did
  not make. See docs/findings-agents.md.
- With `--cache`, the same answer reached by two workers at once is asked
  once. Before, both could miss the cache and both called the judge.

## 0.1.0

First release.

- Controls that are wrong by construction: no answer, grader attacks, another
  item's reference (plain and dressed), dosed edits of the reference for
  prose and for JSON answers, and your own labeled answers.
- Graders as a Python function, a shell command, or an Inspect AI task.
- A profile of what the grader notices: missing content, off-topic content,
  a wrong number, a reversed claim, self-contradiction.
- Leak rates with exact intervals, a detection threshold, order violations
  and dressing lift.
- A verdict cache and retries for paid judges.
- `knownbad diff` to compare two runs of the same controls, with an exact
  paired test.
- A terminal report and a single-file HTML report read as a plate of controls.
- `check()` for use inside a test suite, and a GitHub Action.
- Exit codes for CI and a frozen controls file.
- One check, "could this be a right answer", guards every control that is
  called wrong. It was tightened after an independent review found twelve
  cases where a claim could be false.
