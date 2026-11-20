"""Read and write the two file kinds: JSON Lines for items and controls, JSON for a run."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .model import Control, Item


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{number}: not valid JSON ({error.msg})") from error
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{number}: each line must be a JSON object")
            rows.append(row)
    return rows


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    # "\n" on every platform: a frozen controls file must be the same bytes anywhere.
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_items(path: str | Path) -> list[Item]:
    return [Item.from_dict(row) for row in read_jsonl(path)]


def read_controls(path: str | Path) -> list[Control]:
    return [Control.from_dict(row) for row in read_jsonl(path)]


def write_controls(path: str | Path, controls: Iterable[Control]) -> None:
    write_jsonl(path, (c.to_dict() for c in controls))


def read_harvested(path: str | Path, items: dict[str, Item]) -> list[Control]:
    """Answers a person or a deterministic check already labeled.

    Each line: {"item_id": ..., "answer": ..., "expect": "fail" | "pass", "note": ...}
    """
    controls: list[Control] = []
    for index, row in enumerate(read_jsonl(path), start=1):
        item_id = str(row.get("item_id", ""))
        if item_id not in items:
            raise ValueError(f"{path}:{index}: no item with id {item_id!r}")
        expect = row.get("expect", "fail")
        if expect not in ("fail", "pass"):
            raise ValueError(f"{path}:{index}: expect must be 'fail' or 'pass'")
        if "answer" not in row:
            raise ValueError(f"{path}:{index}: missing 'answer'")
        controls.append(
            Control(
                id=f"{item_id}::harvested@{index}",
                item_id=item_id,
                family="harvested" if expect == "fail" else "harvested-good",
                level="4",
                expect=expect,
                answer=str(row["answer"]),
                how=str(row.get("note") or "Labeled by hand or by a deterministic check."),
            )
        )
    return controls


def write_json(path: str | Path, data: Any) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=1) + "\n")


def write_text(path: str | Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
