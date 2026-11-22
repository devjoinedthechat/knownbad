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
rate for an incomplete answer from 40% to 0%. Over three trials it was 33%
to 9% ([section 4](#4-over-three-trials)).

### What that does to a score

Take two systems on the same items.

- **A** gives the complete right answer on half the items and no answer on
  the rest. It is fully right half the time.
- **B** answers every item and leaves one sentence out every time. It is
  never fully right.

A scores 50% under every judge here, because each passed every reference and
failed every empty answer. B's score is the "sentence removed" column.

| Judge | A | B, with its 95% interval |
|---|---|---|
| `langchain-qa · Haiku 5.5` | 50% | 53% (38%–69%) |
| `langchain-cot-qa · Haiku 5.5` | 50% | 51% (35%–67%) |
| `promptfoo-rubric · Haiku 5.5` | 50% | 51% (35%–67%) |
| `naive · Sonnet 5.5` | 50% | 47% (21%–73%) |
| `naive · Haiku 5.5` | 50% | 40% (25%–56%) |
| `inspect-fact · Haiku 5.5` | 50% | 9% (3%–22%) |
| `inspect-qa · Haiku 5.5` | 50% | 5% (1%–16%) |
| `inspect-fact · Sonnet 5.5` | 50% | 0% (0%–22%) |
| `inspect-qa · Sonnet 5.5` | 50% | 0% (0%–22%) |
| `strict · Haiku 5.5` | 50% | 0% (0%–8%) |

Under the first three, B scores level with A. Under `strict` and Inspect's scorers B scores close to
nothing. Which of the two is right depends on whether a partial answer is
acceptable in your eval. The point is that the judge prompt made that choice,
and the score does not say so.

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

## 4. Over three trials

Sections 1 to 3 graded each control once. This run, on 2026-11-22, graded the
smallest edits three times each on all seven Haiku 5.5 judges.

It is not the same setup, so compare the pattern, not single numbers:

- The calls went through the Claude Code CLI on a Claude subscription. It
  adds about 1,000 tokens of its own context to every call.
- The controls were rebuilt with the current knownbad, so a few counts
  differ (48 reversed words, not 45).

It used 11.8 million tokens, and every call got a verdict.

| Judge | Sentence removed, by majority | Each trial | Same verdict all three times |
|---|---|---|---|
| `langchain-cot-qa` | 58% (42%–73%) | 58%, 53%, 56% | 93% (40 of 43) |
| `langchain-qa` | 37% (23%–53%) | 44%, 26%, 40% | 74% (32 of 43) |
| `promptfoo-rubric` | 37% (23%–53%) | 35%, 30%, 40% | 79% (34 of 43) |
| `naive` | 33% (19%–49%) | 33%, 30%, 33% | 84% (36 of 43) |
| `strict` | 9% (3%–22%) | 5%, 16%, 9% | 84% (36 of 43) |
| `inspect-fact` | 7% (1%–19%) | 7%, 5%, 5% | 95% (41 of 43) |
| `inspect-qa` | 7% (1%–19%) | 5%, 7%, 5% | 95% (41 of 43) |

"By majority" counts an answer as passed when two of its three verdicts
passed it.

- **The split holds.** The same four judges passed a third or more of the
  incomplete answers in every trial. Inspect's two stayed at 7% or under in
  every trial. No judge changed sides.
- **Mid-range rates move.** `langchain-qa` went from 44% to 26% to 40% on
  the same 43 answers, and a quarter of its verdicts on them changed between
  trials. Quote a rate like that from repeats, or with its interval.
- **`strict` is not zero here.** It passed 5% to 16% per trial. Wording still
  decides most of it: `naive` passed 33%.
- **The score example holds in shape.** System B from
  section 2 would score 37% under `langchain-qa` here, not 53%. A prompt
  still sets a partial answer's score to a third or more under four judges
  and near zero under three; the exact tie with A was one trial.
- **Wrong content is caught steadily.** For a changed number, a reversed
  word and an added contradiction, no judge passed more than 7% by majority,
  and at least 92% of those answers got the same verdict all three times.
  `inspect-qa` passed 7% of contradictions (5 of 73), against 14% in one
  trial.
- **References.** Every judge passed all 74 by majority. Of the 1,554
  single verdicts on them, three failed: two from `inspect-qa`, one from
  `naive`.

The counts are in
[tallies-repeat.json](../study/judges/tallies-repeat.json).

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
  before trusting a pass rate. A judge that ignores omissions passes about
  half of the answers that leave a third of the content out.
- The first study pass and the example in this repo show where plainly wrong
  answers do pass: graders built on word overlap or pattern matching, and
  verdict parsing in home-made judges.

## Limits

- Two models from one family. Smaller, older or local judge models were not
  tested and may behave differently.
- Synthetic items written for the study, in English, with clean references.
- "0 of 6,283" is many controls from few items. Counted by item, as the
  report now does, zero leaks puts one judge's rate under 5% on its 74 items
  and under 14% for the three judges that ran on 25.
- One trial per control in sections 1 to 3. Section 4 repeats the smallest
  edits three times: rates near zero stayed near zero, and rates in the
  middle moved by up to 18 points between trials.
- Section 4 ran through Claude Code, which adds its own context to each
  call, so its rates are not a straight rerun of the API run.
- Three of the ten judges ran on a third of the items, so their intervals
  are wide.
- The promptfoo rubric wording and both `naive` and `strict` prompts are ours.
