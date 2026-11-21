import json

import pytest

from knownbad.cli import main
from knownbad.compare import compare, regressions
from knownbad.report import render_diff
from knownbad.stats import sign_test


@pytest.fixture()
def runs(tmp_path, items_path, graders_path):
    controls = tmp_path / "controls.jsonl"
    main(["gen", items_path, "-o", str(controls)])
    paths = {}
    for grader in ("loose", "careful", "exact"):
        paths[grader] = tmp_path / f"{grader}.json"
        main(
            [
                "run",
                items_path,
                "--controls",
                str(controls),
                "--grader",
                f"{graders_path}:{grader}",
                "-q",
                "-o",
                str(paths[grader]),
            ]
        )
    return paths


def load(path):
    return json.loads(path.read_text())


def test_sign_test_matches_known_values():
    assert sign_test(0, 0) is None
    assert sign_test(5, 5) == 1.0
    assert sign_test(10, 0) == pytest.approx(2 * 0.5**10)
    assert sign_test(1, 9) == pytest.approx(2 * (1 + 10) * 0.5**10)
    assert sign_test(3, 4) == sign_test(4, 3)


def test_a_better_grader_shows_as_fixes_and_no_regressions(runs):
    diff = compare(load(runs["loose"]), load(runs["careful"]))
    assert diff["direction"] == "better" and diff["p_value"] < 0.001
    assert len(diff["moves"]["fixed"]) == 50 and diff["moves"]["broken"] == []
    assert diff["leaks"]["old"]["k"] == 50 and diff["leaks"]["new"]["k"] == 0
    assert "refund-window::numbers@1" in diff["moves"]["now_fails"]
    assert regressions(diff) == []


def test_the_test_counts_items_not_controls(runs):
    old = load(runs["careful"])
    new = load(runs["careful"])
    # Six wrong answers of one item start to pass. Counted as six flips that
    # would be p = 0.03; they are one item's verdicts, and one item shows nothing.
    item = old["outcomes"][0]["control"]["item_id"]
    turned = 0
    for outcome in new["outcomes"]:
        control = outcome["control"]
        if control["item_id"] == item and control["expect"] == "fail" and turned < 6:
            outcome["verdicts"] = [{"passed": True}]
            turned += 1
    diff = compare(old, new)
    assert len(diff["moves"]["broken"]) == 6 and diff["direction"] == "worse"
    assert diff["items"] == {"better": 0, "worse": 1, "mixed": 0}
    assert diff["p_value"] == 1.0
    assert diff["leaks"]["new"]["items"] == 24
    assert regressions(diff) == ["6 wrong answers that were caught now pass"]


def test_fixes_and_breaks_inside_one_item_cancel(runs):
    old, new = load(runs["careful"]), load(runs["careful"])
    item = old["outcomes"][0]["control"]["item_id"]
    mine = [
        i
        for i, o in enumerate(old["outcomes"])
        if o["control"]["item_id"] == item and o["control"]["expect"] == "fail"
    ][:2]
    old["outcomes"][mine[0]]["verdicts"] = [{"passed": True}]  # fixed in new
    new["outcomes"][mine[1]]["verdicts"] = [{"passed": True}]  # broken in new
    diff = compare(old, new)
    assert diff["items"] == {"better": 0, "worse": 0, "mixed": 1}
    assert diff["p_value"] is None
    assert "cancel out within each item" in render_diff(diff)


def test_a_worse_grader_is_a_regression(runs):
    diff = compare(load(runs["careful"]), load(runs["loose"]))
    assert diff["direction"] == "worse"
    assert regressions(diff) == ["50 wrong answers that were caught now pass"]


def test_a_run_compared_with_itself_has_no_moves(runs):
    diff = compare(load(runs["loose"]), load(runs["loose"]))
    assert diff["direction"] == "same" and diff["p_value"] is None
    assert not any(diff["moves"].values())


def test_controls_missing_from_one_run_or_without_a_verdict_are_set_aside(runs):
    old, new = load(runs["loose"]), load(runs["careful"])
    new["outcomes"] = new["outcomes"][10:]
    old["outcomes"][20]["verdicts"] = [{"error": "timeout"}]
    diff = compare(old, new)
    assert diff["only_old"] == 10 and diff["only_new"] == 0
    assert diff["unreadable"] == [old["outcomes"][20]["control"]["id"]]


def test_runs_from_different_controls_are_refused(runs):
    old, new = load(runs["loose"]), load(runs["careful"])
    new["outcomes"][5]["control"]["answer"] += " changed"
    with pytest.raises(ValueError, match="different answer"):
        compare(old, new)


def test_cli_prints_the_change_and_gates_on_regressions(runs, tmp_path, capsys):
    assert main(["diff", str(runs["loose"]), str(runs["careful"]), "--fail-on-regression"]) == 0
    text = capsys.readouterr().out
    assert "Wrong answers that passed   17% → 0%   (50 → 0 of 288)" in text
    assert "50 fixed, 0 broken: the grader is better" in text
    assert "24 items better, 0 worse (p < 0.001, unlikely to be chance)" in text

    saved = tmp_path / "diff.json"
    code = main(
        [
            "diff",
            str(runs["careful"]),
            str(runs["loose"]),
            "--fail-on-regression",
            "--json",
            str(saved),
            "-q",
        ]
    )
    assert code == 1
    assert "were caught now pass" in capsys.readouterr().err
    assert json.loads(saved.read_text())["direction"] == "worse"
    assert main(["diff", str(runs["careful"]), str(runs["loose"]), "-q"]) == 0

    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    assert main(["diff", str(bad), str(runs["loose"])]) == 2
