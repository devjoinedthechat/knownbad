# The numbers and how to read them

## Leak rate

The share of `fail` controls that passed. It comes with an exact
(Clopper-Pearson) 95% interval, which never claims more than the data
supports.

**It is a floor.** Controls are easier to catch than real near-misses, so the
grader's true false-accept rate is at least this high.

### How many items for a claim

Zero leaks does not mean a zero rate. With no leaks at all, the upper end of
the interval is roughly 3.7 divided by the number of must-fail controls.

| Must-fail controls, zero leaks | Leak rate is under |
|---|---|
| 24 | 14% |
| 100 | 3.6% |
| 300 | 1.2% |
| 1,000 | 0.4% |

Each item yields about ten must-fail controls, so 30 items support a claim of
about 1%. They are not independent draws: controls of one item share its
question, so treat the interval as optimistic for small sets.

## Detection threshold

Dose controls corrupt a growing share of the reference. The threshold is the
first dose range in which the grader fails at least half the answers.

| Reading | Meaning |
|---|---|
| `≤25%` | Fails most answers at the smallest edit |
| `50–75%` | Needs more than half the answer wrong before it notices |
| `never` | Still passes most answers with everything changed |

Doses fall into four ranges. An item with three sentences has doses of one
third, two thirds and all, so it has no reading in the lowest range.

## Order violations

A dose control must not score above the step before it. A violation means
the grader rewarded a more damaged answer. With repeated trials the mean
score is compared, so noise is averaged out first.

## Dressing lift

For each item the plain and the dressed transplant are the same wrong answer.
The lift is the dressed leak rate minus the plain one. "Turned" counts the
answers the grader caught plain and passed dressed.

## Same verdict every trial

With `--trials 2` or more, the share of answers that got the same verdict
each time. A split verdict means the grader is guessing on that answer. The
majority is used for every other number, and a tie counts as a pass.

## Comparing two runs

`knownbad diff` pairs each control with itself across two runs. Only controls
whose verdict flipped carry information, so the test is an exact sign test on
the flips (McNemar's exact test).

- `p` under 0.05: a split this uneven is unlikely if the grader had not changed.
- Five fixes and no breaks give `p = 0.06`. Small sets cannot show small changes.

## What voids a run

- The grader returned no verdict for any control.
- Fewer than half the references passed.
- No must-fail control was graded.

A control with no verdict is never counted as caught. It is left out of
every rate and reported separately.
