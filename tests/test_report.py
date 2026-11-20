import json

from knownbad.cli import main
from knownbad.report.html import render


def result_for(tmp_path, items_path, graders_path, grader, extra=()):
    out = tmp_path / f"{grader}.json"
    main(["run", items_path, "--grader", f"{graders_path}:{grader}", "-q", "-o", str(out), *extra])
    return json.loads(out.read_text())


def test_report_is_one_file_with_no_outside_requests(tmp_path, items_path, graders_path):
    page = render(result_for(tmp_path, items_path, graders_path, "loose"))
    assert page.startswith("<!doctype html>")
    for outside in ("http://", "https://", "<link", "src="):
        assert outside not in page


def test_answers_are_escaped_not_run(tmp_path, items_path, graders_path):
    page = render(result_for(tmp_path, items_path, graders_path, "loose"))
    assert "&lt;/answer&gt;" in page
    assert "</answer>" not in page
    assert page.count("<script>") == 1


def test_report_shows_leaks_threshold_and_dressing(tmp_path, items_path, graders_path):
    page = render(result_for(tmp_path, items_path, graders_path, "loose"))
    assert "50 of 288 wrong answers passed" in page
    assert "Leaked controls · 50" in page
    assert "Detection threshold, numbers" in page and ">never<" in page
    assert "The answer states it was verified." in page
    assert page.count("<details") == 50


def test_clean_and_void_runs_say_so(tmp_path, items_path, graders_path):
    clean = render(result_for(tmp_path, items_path, graders_path, "careful"))
    assert "No wrong answer passed" in clean and "<details" not in clean
    bad = tmp_path / "bad.py"
    bad.write_text("def never(item, answer):\n    return False\n")
    out = tmp_path / "void.json"
    main(["run", items_path, "--grader", f"{bad}:never", "-q", "-o", str(out)])
    void = render(json.loads(out.read_text()))
    assert "Void run" in void and "Right answers that failed · 24" in void


def test_run_and_report_write_the_html_file(tmp_path, items_path, graders_path, capsys):
    page = tmp_path / "r.html"
    saved = tmp_path / "r.json"
    args = ["run", items_path, "--grader", f"{graders_path}:loose", "-q"]
    assert main([*args, "--html", str(page), "-o", str(saved)]) == 0
    first = page.read_text()
    assert main(["report", str(saved), "--html", str(page)]) == 0
    assert page.read_text() == first
