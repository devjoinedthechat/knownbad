# Quoted prompts

`judges.py` quotes grading prompts from two projects so they can be tested as
their users run them.

| Prompt | Project | Licence |
|---|---|---|
| `LANGCHAIN_QA`, `LANGCHAIN_COT_QA` | LangChain, `langchain_classic/evaluation/qa/eval_prompt.py` | MIT, Copyright (c) LangChain, Inc. |
| `PROMPTFOO_SYSTEM`, `PROMPTFOO_USER` | promptfoo, `src/prompts/grading.ts` | MIT, Copyright (c) Promptfoo |

Inspect AI's scorers are imported from the installed package, not copied.
