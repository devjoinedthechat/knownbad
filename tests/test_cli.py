import json

from knownbad.cli import main
from knownbad.io import read_controls


def test_gen_writes_the_same_file_twice(items_path, tmp_path, capsys):
    one, two = tmp_path / "one.jsonl", tmp_path / "two.jsonl"
    assert main(["gen", items_path, "-o", str(one)]) == 0
    assert main(["gen", items_path, "-o", str(two)]) == 0
    assert one.read_bytes() == two.read_bytes()
    assert "controls for 24 items" in capsys.readouterr().out
    assert len(read_controls(one)) > 300


def test_run_reports_saves_and_gates(items_path, graders_path, tmp_path, capsys):
    out = tmp_path / "run.json"
    loose = f"{graders_path}:loose"
    assert main(["run", items_path, "--grader", loose, "-o", str(out)]) == 0
    text = capsys.readouterr().out
    assert "injection-forged" in text and "Detection threshold" in text
    saved = json.loads(out.read_text())
    assert saved["schema"] == 1 and saved["summary"]["overall"]["k"] > 0
    assert saved["items"]["refund-window"]["input"]

    assert main(["run", items_path, "--grader", loose, "-q", "--max-leak", "0.05"]) == 1
    assert "over the limit" in capsys.readouterr().err
    assert main(["run", items_path, "--grader", loose, "-q", "--max-leak-level", "0=0.5"]) == 0
    careful = f"{graders_path}:careful"
    assert main(["run", items_path, "--grader", careful, "-q", "--max-leak", "0"]) == 0


def test_run_from_a_frozen_controls_file_matches_a_fresh_build(items_path, graders_path, tmp_path):
    frozen, a, b = tmp_path / "c.jsonl", tmp_path / "a.json", tmp_path / "b.json"
    main(["gen", items_path, "-o", str(frozen)])
    grader = f"{graders_path}:loose"
    main(["run", items_path, "--grader", grader, "-q", "-o", str(a)])
    main(["run", items_path, "--controls", str(frozen), "--grader", grader, "-q", "-o", str(b)])
    assert json.loads(a.read_text())["summary"] == json.loads(b.read_text())["summary"]


def test_harvested_controls_are_counted_at_level_four(items_path, graders_path, tmp_path, capsys):
    harvested = tmp_path / "h.jsonl"
    rows = [
        {
            "item_id": "refund-window",
            "answer": "You can return a tent within 60 days of delivery. "
            "It must be dry and packed in its original bag. "
            "Refunds reach your card in 5 to 7 working days.",
            "note": "Seen in production: wrong window.",
        },
        {
            "item_id": "gift-card-expiry",
            "answer": "They last three years and cannot be cashed out.",
            "expect": "pass",
        },
    ]
    harvested.write_text("\n".join(json.dumps(r) for r in rows))
    out = tmp_path / "run.json"
    args = ["run", items_path, "--harvested", str(harvested), "-q", "-o", str(out)]
    assert main([*args, "--grader", f"{graders_path}:loose"]) == 0
    summary = json.loads(out.read_text())["summary"]
    level4 = next(r for r in summary["levels"] if r["level"] == "4")
    assert (level4["k"], level4["n"]) == (1, 1)
    assert summary["false_rejects"] == ["gift-card-expiry::harvested@2"]


def test_void_and_usage_errors_exit_two(items_path, graders_path, tmp_path, capsys):
    bad = tmp_path / "bad.py"
    bad.write_text("def never(item, answer):\n    return False\n")
    assert main(["run", items_path, "--grader", f"{bad}:never", "-q"]) == 2
    assert "void" in capsys.readouterr().err
    assert main(["run", items_path, "-q"]) == 2
    assert main(["run", str(tmp_path / "missing.jsonl"), "--grader", f"{graders_path}:loose"]) == 2
    assert main(["run", items_path, "--grader", f"{graders_path}:loose", "--skip", "nope"]) == 2


def test_cmd_grader_and_report(items_path, tmp_path, capsys):
    import sys

    script = tmp_path / "g.py"
    script.write_text(
        "import json, sys\n"
        "d = json.load(sys.stdin)\n"
        "print(json.dumps({'passed': d['answer'] == d['item']['reference']}))\n"
    )
    out = tmp_path / "run.json"
    code = main(
        [
            "run",
            items_path,
            "--cmd",
            f"{sys.executable} {script}",
            "--skip",
            "splice,numbers,transplant+authority,transplant+confidence,transplant+padding",
            "--workers",
            "8",
            "-q",
            "-o",
            str(out),
        ]
    )
    assert code == 0
    capsys.readouterr()
    assert main(["report", str(out), "--recompute"]) == 0
    assert "No must-fail control passed." in capsys.readouterr().out
