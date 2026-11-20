# Security

## What knownbad runs

- `--grader FILE.py:FUNC` imports and runs your Python file.
- `--cmd COMMAND` runs your shell command once per control.
- `knownbad inspect` runs your Inspect AI task.

These are your own code and run with your permissions. Do not point knownbad
at a grader you would not run directly.

## What it handles as data

Items, controls and result files are read as data and never executed. The
HTML report escapes every answer and embeds the run as inert JSON, so an
answer that contains markup or a script cannot run when the report is opened.
The report makes no network requests.

Some controls are prompt injections by design. They are sent only to the
grader you name.

## Reporting a problem

Open a private security advisory on the GitHub repository. Please include a
result file or a minimal item that reproduces the problem.
