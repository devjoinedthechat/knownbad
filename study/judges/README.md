# Judge study: do published judge prompts accept wrong answers?

This is the test that decides what knownbad may claim. It runs the controls
against judge prompts people actually copy, with real judge models, and counts
what passes.

## What is tested

| Judge | Source |
|---|---|
| `inspect-qa` | Inspect AI `model_graded_qa()`, as shipped |
| `inspect-fact` | Inspect AI `model_graded_fact()`, as shipped |
| `langchain-qa` | LangChain QA eval prompt |
| `langchain-cot-qa` | LangChain chain-of-thought QA eval prompt |
| `promptfoo-rubric` | promptfoo default grading prompt, with a plain "agrees with this reference" rubric |
| `naive` | A five-line judge of our own, the kind written on day one |
| `strict` | The same judge with the rule spelled out: every fact, nothing left out, no contradiction |

- **Models**: every judge on Claude Haiku 5.5; three judges on Claude Sonnet 5.5,
  on every third item, because it costs about twenty times more per token.
- **Items**: three synthetic sets, 74 items. A shop's support answers, short
  factual answers, and operations runbooks. Every number in them is a fact
  the answer depends on.
- **Controls**: all levels knownbad builds, about 16 per item.

## The bar, set before the run

The claim "published graders accept wrong answers" survives if **at least
three graders** are over either bar:

| Bar | Threshold |
|---|---|
| Wrong answers of levels 1 to 3 that pass | 5% or more |
| Answers with one number changed that pass | 10% or more |

Fewer than three means the claim is dropped. knownbad then stays a check
for home-made graders, which is where the example run shows it bites.

## Run it

```bash
pip install -e ".[inspect]" anthropic
python study/judges/run.py --dry-run       # offline: checks the pipeline end to end
export ANTHROPIC_API_KEY=...
python study/judges/run.py --cap 10        # stops before spending more than $10
python study/judges/summarise.py
```

Each finished cell is a normal result file in `results/`. A stopped run
resumes where it left off, and any cell opens as a report:

```bash
knownbad report study/judges/results/facts__naive__claude-haiku-5-5.json --html cell.html
```

## Limits

- Synthetic items, written for this study. Real eval sets are messier.
- One trial per control. Judges vary between calls; rates near a bar need
  repeats before they are quoted.
- Inspect scores a reply it cannot parse as incorrect. That counts here as a
  caught control, because it is what an Inspect user would get.
- The promptfoo rubric wording is ours. promptfoo leaves the rubric to the user.
