# Quoted prompts

`run_judges.py` quotes grading prompts so they can be tested as their users
run them.

| Prompt | Project | Licence |
|---|---|---|
| `TRAJECTORY_ACCURACY_PROMPT_WITH_REFERENCE`, `TRAJECTORY_ACCURACY_PROMPT` | LangChain agentevals, `python/agentevals/trajectory/llm.py` (commit 946ad15) | MIT, Copyright (c) LangChain, Inc. |
| `OPENEVALS_SCHEMA` field descriptions, `openevals_string` | LangChain openevals, `python/openevals/llm.py` and `utils.py` (commit 561ba69) | MIT, Copyright (c) LangChain, Inc. |
| `DEEPEVAL_EXTRACT`, `DEEPEVAL_VERDICT` | DeepEval, `deepeval/metrics/task_completion/templates/` (commit aeb529e) | Apache-2.0, Copyright (c) Confident AI |

Inspect AI's scorer is imported from the installed package, not copied.
