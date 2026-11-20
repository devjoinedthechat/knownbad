import json
import threading

from knownbad import build, python_grader, run
from knownbad.cache import Cache, fingerprint
from knownbad.cli import main
from knownbad.model import Item, Verdict

ITEMS = [
    Item(id="a", input="How many days?", reference="Within 30 days. No fee applies."),
    Item(id="b", input="What fee?", reference="The fee is 4 euros. It is taken at once."),
]


def counting(fail_first=0):
    lock, state = threading.Lock(), {"calls": 0}

    def grade(item, answer):
        with lock:
            state["calls"] += 1
            if state["calls"] <= fail_first:
                raise TimeoutError("busy")
        return answer == item["reference"]

    return grade, state


def test_a_second_run_asks_only_for_what_is_missing(tmp_path):
    controls, by_id = build(ITEMS), {i.id: i for i in ITEMS}
    # Two controls of one item can be the same answer; that answer is asked once.
    distinct = len({(c.item_id, c.answer) for c in controls})
    grade, state = counting()
    first = run(controls, by_id, python_grader(grade), cache=Cache(tmp_path / "c.jsonl", "g1"))
    assert state["calls"] == distinct

    again = Cache(tmp_path / "c.jsonl", "g1")
    second = run(controls, by_id, python_grader(grade), cache=again)
    assert state["calls"] == distinct and again.hits == len(controls)
    assert [o.to_dict() for o in first] == [o.to_dict() for o in second]

    changed = Cache(tmp_path / "c.jsonl", "g2")  # a different grader: no hits from g1
    run(controls, by_id, python_grader(grade), cache=changed)
    assert state["calls"] == 2 * distinct


def test_trials_are_cached_one_by_one_and_errors_are_never_cached(tmp_path):
    cache = Cache(tmp_path / "c.jsonl", "g")
    control = build(ITEMS)[0]
    keys = {cache.key(ITEMS[0], control, trial) for trial in range(3)}
    assert len(keys) == 3
    cache.put(next(iter(keys)), Verdict(passed=None, error="boom"))
    assert not (tmp_path / "c.jsonl").exists()


def test_a_line_cut_off_by_a_crash_is_skipped(tmp_path):
    path = tmp_path / "c.jsonl"
    cache = Cache(path, "g")
    key = cache.key(ITEMS[0], build(ITEMS)[0], 0)
    cache.put(key, Verdict(passed=True, score=1.0))
    with open(path, "a") as handle:
        handle.write('{"key": "half-written", "verd')
    reopened = Cache(path, "g")
    assert reopened.get(key) == Verdict(passed=True, score=1.0)


def test_no_verdict_is_asked_for_again(tmp_path):
    controls, by_id = build(ITEMS)[:4], {i.id: i for i in ITEMS}
    grade, state = counting(fail_first=3)
    outcomes = run(controls, by_id, python_grader(grade), workers=1, retries=3, retry_wait=0)
    assert not any(o.errored for o in outcomes) and state["calls"] == 4 + 3
    grade, state = counting(fail_first=100)
    outcomes = run(controls, by_id, python_grader(grade), workers=1, retries=1, retry_wait=0)
    assert all(o.errored for o in outcomes) and state["calls"] == 8


def test_the_fingerprint_follows_the_graders_source(tmp_path):
    grader = tmp_path / "g.py"
    grader.write_text("def judge(item, answer):\n    return True\n")
    before = fingerprint(f"{grader}:judge", None, 0.5)
    assert before == fingerprint(f"{grader}:judge", None, 0.5)
    assert before != fingerprint(f"{grader}:judge", None, 0.7)
    grader.write_text("def judge(item, answer):\n    return False\n")
    assert before != fingerprint(f"{grader}:judge", None, 0.5)
    assert fingerprint(None, "node a.mjs", 0.5) != fingerprint(None, "node b.mjs", 0.5)


def test_cli_cache_round_trip(tmp_path, items_path, graders_path, capsys):
    cache, out = tmp_path / "cache.jsonl", tmp_path / "run.json"
    args = ["run", items_path, "--grader", f"{graders_path}:loose", "--cache", str(cache)]
    assert main([*args, "-o", str(out)]) == 0
    first = json.loads(out.read_text())["summary"]
    assert " of 493 verdicts came from" in capsys.readouterr().out
    assert main([*args, "-o", str(out)]) == 0
    assert "493 of 493 verdicts came from" in capsys.readouterr().out
    assert json.loads(out.read_text())["summary"] == first
