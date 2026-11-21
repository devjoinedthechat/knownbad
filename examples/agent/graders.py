"""Two stand-in graders for agent runs. Neither calls a model.

    knownbad run examples/agent/items.jsonl --grader examples/agent/graders.py:reads_the_reply

An answer here is a run: the tool calls an agent made and its closing message.
"""

import json


def _run(answer):
    try:
        run = json.loads(answer)
    except ValueError:
        return None
    return run if isinstance(run, dict) and isinstance(run.get("calls"), list) else None


def reads_the_reply(item, answer):
    """Grades the closing message and nothing else.

    This is what a judge does when it is shown the conversation without the
    tool calls, or told to check "did the agent resolve the request".
    """
    run, wanted = _run(answer), json.loads(item["reference"])
    if run is None:
        return {"passed": False, "explanation": "Not a run."}
    same = run.get("final", "").strip() == wanted.get("final", "").strip()
    return {"passed": same, "explanation": "Compared the closing message with the reference's."}


def reads_the_calls(item, answer):
    """Wants the reference's calls, with their arguments, to have succeeded, and no others.

    It knows a failed call by the two shapes these example tools use: an
    "error" field, or text that starts with "Error". Your tools have their own.
    """
    run, wanted = _run(answer), json.loads(item["reference"])
    if run is None:
        return {"passed": False, "explanation": "Not a run."}

    def done(calls):
        return sorted(
            json.dumps([call.get("tool"), call.get("args", {})], sort_keys=True)
            for call in calls
            if isinstance(call, dict) and not _is_error(call.get("result"))
        )

    if done(run["calls"]) != done(wanted["calls"]):
        return {"passed": False, "explanation": "The calls that succeeded are not the reference's."}
    same = run.get("final", "").strip() == wanted.get("final", "").strip()
    return {"passed": same, "explanation": "Calls match; compared the closing message."}


def _is_error(result):
    if isinstance(result, dict):
        return "error" in result
    return isinstance(result, str) and result.startswith("Error")
