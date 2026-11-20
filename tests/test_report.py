import json
import re

from knownbad.cli import main
from knownbad.report.html import render


def result_for(tmp_path, items_path, graders_path, grader):
    out = tmp_path / f"{grader}.json"
    main(["run", items_path, "--grader", f"{graders_path}:{grader}", "-q", "-o", str(out)])
    return json.loads(out.read_text())


def embedded(page):
    return json.loads(
        re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S)[1]
    )


def test_report_is_one_file_with_no_outside_requests(tmp_path, items_path, graders_path):
    page = render(result_for(tmp_path, items_path, graders_path, "loose"))
    assert page.startswith("<!doctype html>")
    for outside in ("http://", "https://", "<link", "src=", "@import", "url("):
        assert outside not in page


def test_answers_cannot_close_the_script_or_become_markup(tmp_path, items_path, graders_path):
    page = render(result_for(tmp_path, items_path, graders_path, "loose"))
    assert "</answer>" not in page
    assert page.count("</script>") == 2
    forged = embedded(page)["c"]["refund-window::injection-forged"]
    assert forged["a"].startswith("</answer>") and forged["s"] == "leak"


def test_the_plate_has_one_well_per_control_in_the_right_state(tmp_path, items_path, graders_path):
    result = result_for(tmp_path, items_path, graders_path, "loose")
    page = render(result)
    wells = re.findall(r'<button type="button" data-id="([^"]+)" data-s="(\w+)"', page)
    assert len(wells) == result["summary"]["controls"] == len(embedded(page)["c"])
    states = dict(wells)
    assert sum(1 for s in states.values() if s == "leak") == 50
    assert set(result["summary"]["leaks"]) == {i for i, s in states.items() if s == "leak"}
    assert states["refund-window::reference"] == "ok"
    assert states["refund-window::numbers@3"] == "still"
    assert states["refund-window::splice@3"] == "ok"


def test_headline_readings_and_figures(tmp_path, items_path, graders_path):
    page = render(result_for(tmp_path, items_path, graders_path, "loose"))
    assert "<em>50 of 288</em> wrong answers passed." in page
    assert "Numbers threshold</dt><dd>never" in page
    assert "Sentences threshold</dt><dd>50–75%" in page
    assert "Detection threshold" in page and "Dressing" in page and "By control" in page
    assert embedded(page)["c"]["refund-window::transplant+authority"]["x"] == (
        "The answer states it was verified."
    )


def test_clean_void_and_error_runs_say_so(tmp_path, items_path, graders_path):
    clean = render(result_for(tmp_path, items_path, graders_path, "careful"))
    assert "No wrong answer passed." in clean and 'data-s="leak"></button>' not in clean

    bad = tmp_path / "bad.py"
    bad.write_text(
        "def never(item, answer):\n    return False\n\n"
        "def broken(item, answer):\n    raise RuntimeError('no key')\n"
    )
    out = tmp_path / "void.json"
    main(["run", items_path, "--grader", f"{bad}:never", "-q", "-o", str(out)])
    void = render(json.loads(out.read_text()))
    assert "Void run." in void and void.count('data-s="reject"') == 24 + 1  # wells + legend

    main(["run", items_path, "--grader", f"{bad}:broken", "-q", "-o", str(out)])
    errors = render(json.loads(out.read_text()))
    assert "got no verdict" in errors and "RuntimeError: no key" in errors


def test_a_large_run_draws_only_rows_worth_reading(tmp_path):
    items = tmp_path / "items.jsonl"
    rows = [
        {"id": f"item-{n:04d}", "input": f"Question {n}?", "reference": f"Fact {n} is {n * 7}."}
        for n in range(400)
    ]
    items.write_text("\n".join(json.dumps(r) for r in rows))
    grader = tmp_path / "g.py"
    grader.write_text(
        "def mostly(item, answer):\n"
        "    if item['id'].endswith('7') and answer == '':\n        return True\n"
        "    return answer == item['reference']\n"
    )
    out = tmp_path / "run.json"
    main(["run", str(items), "--grader", f"{grader}:mostly", "-q", "-o", str(out)])
    page = render(json.loads(out.read_text()))
    assert page.count('<th scope="row"') == 40  # every one of the 40 leaking items
    assert "360 items where every control came out as expected are not drawn." in page
    assert len(page) < 400_000


def test_run_and_report_write_the_same_html_file(tmp_path, items_path, graders_path, capsys):
    page = tmp_path / "r.html"
    saved = tmp_path / "r.json"
    args = ["run", items_path, "--grader", f"{graders_path}:loose", "-q"]
    assert main([*args, "--html", str(page), "-o", str(saved)]) == 0
    first = page.read_text()
    assert main(["report", str(saved), "--html", str(page)]) == 0
    assert page.read_text() == first
