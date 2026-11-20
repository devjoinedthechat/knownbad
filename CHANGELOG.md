# Changelog

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
