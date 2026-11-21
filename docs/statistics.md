# The numbers and how to read them

## Leak rate

The share of `fail` controls that passed, with an exact 95% interval.

**It is a floor.** Controls are easier to catch than real near-misses, so the
grader's true false-accept rate is at least this high.

### The interval counts items, not controls

An item yields about ten must-fail controls. They share its question and its
reference, so they are not ten independent draws: a grader that misreads one
item tends to leak several of its controls at once.

The interval therefore treats each item as one draw and the share of its
controls that leaked as the value drawn. It is the Clopper-Pearson interval
with the item count in place of the control count.

- With one control per item, as in every row of "What it notices", it is the
  plain exact interval.
- With more, it is wider than an interval over controls would be.
- It needs no estimate of how strongly an item's controls move together, so
  it also works at zero leaks, where there is nothing to estimate that from.

How often each interval contains the true rate: 1,500 simulated runs per
row, 43 items of 11 controls each. The target is 95%.

| True leak rate | Controls of an item | Over controls | Over items |
|---|---|---|---|
| 1% | independent | 97% | 100% |
| 1% | partly together | 81% | 100% |
| 1% | all together | 0% | 99% |
| 5% | independent | 96% | 100% |
| 5% | partly together | 75% | 100% |
| 5% | all together | 46% | 98% |
| 20% | independent | 96% | 100% |
| 20% | partly together | 73% | 100% |
| 20% | all together | 42% | 97% |
| 50% | independent | 96% | 100% |
| 50% | partly together | 74% | 100% |
| 50% | all together | 44% | 97% |

The interval over items is cautious when controls are in fact independent.
That is the price of holding 95% without knowing whether they are.

The table is the output of
[study/intervals/coverage.py](../study/intervals/coverage.py), and
`tests/test_calibration.py` checks the same thing on every change.

### How many items for a claim

Zero leaks does not mean a zero rate. With no leaks at all, the upper end of
the interval is roughly 3.7 divided by the number of items.

| Items, zero leaks | Leak rate is under |
|---|---|
| 24 | 14% |
| 100 | 3.6% |
| 300 | 1.2% |
| 1,000 | 0.4% |

More controls per item do not narrow it. More items do.

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
score is compared, so noise is averaged out first. Scores are compared only
when both answers have one; otherwise the pass shares are.

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
whose verdict flipped carry information.

The test counts items, for the same reason the interval does. An item is
better when more of its wrong answers were fixed than broken, and worse the
other way round. The p-value is an exact sign test on those two counts
(McNemar's exact test).

- `p` under 0.05: a split this uneven is unlikely if the grader had not changed.
- Five items better and none worse give `p = 0.06`. Small sets cannot show
  small changes.
- Six flips inside one item are one item. They show nothing on their own.

## What voids a run

- The grader returned no verdict for more than half the controls.
- Fewer than half the references got a verdict, or fewer than half passed.
- No must-fail control was graded.

A control with no verdict is never counted as caught. It is left out of
every rate and reported separately.
