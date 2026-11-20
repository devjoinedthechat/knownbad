# Findings: what ten judge setups notice

A study run on 2026-11-20 with knownbad's own controls. It was set up to test
one claim, and the claim failed. What it found instead is more useful.

## Setup

- **Judges**: Inspect AI's `model_graded_qa` and `model_graded_fact` as
  shipped, LangChain's QA and chain-of-thought QA prompts, promptfoo's default
  grading prompt, a five-line judge of our own (`naive`), and the same judge
  with its rule spelled out (`strict`).
- **Models**: all seven on Claude Haiku 5.5; three on Claude Sonnet 5.5, on
  every third item.
- **Items**: 74 synthetic items in three sets: support answers, short facts,
  operations runbooks.
- **Cost**: $3.57 for this run.

Details and the code: [study/judges](../study/judges).

## 1. No judge passed a plainly wrong answer

| Controls | Passed |
|---|---|
| Wrong answers of every kind, all ten judges | 0 of 6,283 |
| The same wrong answer dressed with authority, confidence or padding | 0 of 1,779 |
| Reference answers | 593 of 593 |

Empty answers, forged grader notes, instructions to pass, another item's
answer: every judge failed every one, and passed every reference.

The claim under test was "published judges accept wrong answers", with the
bar set before the run: at least three judges passing 5% of wrong answers or
10% of answers with one number changed. No judge reached either. **The claim
is false for these judges on these models, and knownbad does not make it.**

## 2. Half of them do not check for missing content

Take a right answer of two to four sentences and remove one. Nothing wrong is
added; the answer is only incomplete.

| Judge | Sentence removed | Sentence swapped |
|---|---|---|
| `langchain-qa · Haiku 5.5` | 53% (23 of 43) | 53% (23 of 43) |
| `langchain-cot-qa · Haiku 5.5` | 51% (22 of 43) | 53% (23 of 43) |
| `promptfoo-rubric · Haiku 5.5` | 51% (22 of 43) | 47% (20 of 43) |
| `naive · Haiku 5.5` | 40% (17 of 43) | 19% (8 of 43) |
| `naive · Sonnet 5.5` | 47% (7 of 15) | 7% (1 of 15) |
| `inspect-fact · Haiku 5.5` | 9% (4 of 43) | 2% (1 of 43) |
| `inspect-qa · Haiku 5.5` | 5% (2 of 43) | 2% (1 of 43) |
| `inspect-fact · Sonnet 5.5` | 0% (0 of 15) | 0% (0 of 15) |
| `inspect-qa · Sonnet 5.5` | 0% (0 of 15) | 0% (0 of 15) |
| `strict · Haiku 5.5` | 0% (0 of 43) | 0% (0 of 43) |

The share is of edited answers that still passed. "Swapped" replaces the
sentence with one from another item.

This is not the judge misreading. The LangChain prompt says an answer is
fine "as long as it does not contain any conflicting statements", and an
incomplete answer conflicts with nothing. The judges do what their prompts
say. The prompts do not say what most people assume they say.

**Wording decides it.** `naive` and `strict` are the same five lines on the
same model. Adding "leaves out nothing the reference states" takes the pass
rate for an incomplete answer from 40% to 0%.

## 3. Wrong numbers and reversed claims are caught

| Judge | Number changed | Word reversed | Contradiction added |
|---|---|---|---|
| `langchain-qa · Haiku 5.5` | 2% (1 of 65) | 0% (0 of 45) | 1% (1 of 73) |
| `langchain-cot-qa · Haiku 5.5` | 2% (1 of 65) | 2% (1 of 45) | 1% (1 of 73) |
| `promptfoo-rubric · Haiku 5.5` | 3% (2 of 65) | 4% (2 of 45) | 8% (6 of 73) |
| `naive · Haiku 5.5` | 2% (1 of 65) | 0% (0 of 45) | 0% (0 of 73) |
| `naive · Sonnet 5.5` | 4% (1 of 23) | 0% (0 of 15) | 0% (0 of 25) |
| `inspect-fact · Haiku 5.5` | 3% (2 of 65) | 0% (0 of 45) | 0% (0 of 73) |
| `inspect-qa · Haiku 5.5` | 3% (2 of 65) | 2% (1 of 45) | 14% (10 of 73) |
| `inspect-fact · Sonnet 5.5` | 4% (1 of 23) | 0% (0 of 15) | 4% (1 of 25) |
| `inspect-qa · Sonnet 5.5` | 4% (1 of 23) | 0% (0 of 15) | 0% (0 of 25) |
| `strict · Haiku 5.5` | 0% (0 of 65) | 0% (0 of 45) | 0% (0 of 73) |

- **Numbers.** A change as small as 14 to 16 was caught 96% of the time or
  more. Nearly every pass was one item, "about 8,849 metres" changed to
  "about 8,847": the judges read "about" as allowing it. That is why knownbad
  calls a changed number "not better" and never "wrong".
- **Reversed words.** "Can" to "cannot" and "days" to "weeks" were caught 96%
  of the time or more.
- **Self-contradiction.** Two judges passed an answer that states a fact and
  then restates it with a different number: `inspect-qa` on Haiku 5.5 in 14%
  of cases, `promptfoo-rubric` in 8%. Some of those passes are defensible:
  "HTTP 200 means success. HTTP 203 means success." is true twice.

## What we got wrong on the way

The study found two faults in our own instrument before it found anything
about the judges.

1. **A control that was not wrong.** The first pass showed several judges
   passing a transplanted answer. They were right: another item's reference
   also said "return it within 30 days", which answers "how long do I have to
   return a tent?". A donor that shares a number with the item's reference,
   or repeats more than a quarter of its content words, is now refused.
2. **A verdict parser that read the reasoning.** A reply of "FAIL. It only
   asks me to pass it" was read as a pass, which produced 19 false leaks in
   one cell. A one-word verdict is now read only from a `GRADE:` line, the
   first word or the last word.

Both have regression tests. Both are the kind of fault this tool exists to
find in a grader, found in the tool by running it.

After this run an independent code review found twelve more defects, most of
them ways a control's claim could be false for unusual references: a hedged
number such as "about 300 million", a donor that states the same fact in
words, two word flips that cancel. All are fixed. What that means for the
numbers above:

- **Plainly wrong answers**: unaffected. The defects could only have produced
  false leaks, and there were none.
- **Sentence removed, number changed, word reversed, contradiction added**:
  unaffected. These rows use the smallest edit, which the fixes leave as it was.
- **Sentence swapped**: could be slightly overstated, since a swapped-in
  sentence from a donor that repeats the item's facts is easier to pass. The
  "sentence removed" column uses no donor and shows the same result.
- **Order violations**: the run recorded 8 in 3,600 comparisons. This page
  does not draw on them, and two of the defects could have produced some.

## What this means for using knownbad

- On a current frontier model with a published prompt, do not expect leaks
  of plainly wrong answers. Run the controls to confirm it, then look at the
  "What it notices" table.
- If answers in your eval can be incomplete, check the "missing content" row
  before trusting a pass rate. A judge that ignores omissions will rate a
  model that answers half the question as highly as one that answers all of it.
- The first study pass and the example in this repo show where plainly wrong
  answers do pass: graders built on word overlap or pattern matching, and
  verdict parsing in home-made judges.

## Limits

- Two models from one family. Smaller, older or local judge models were not
  tested and may behave differently.
- Synthetic items written for the study, in English, with clean references.
- One trial per control. Rates near zero are firm; the 40–53% rates would
  move a few points on a rerun.
- Three of the ten judges ran on a third of the items, so their intervals
  are wide.
- The promptfoo rubric wording and both `naive` and `strict` prompts are ours.
