"""Keep verdicts on disk so a stopped run does not pay for the same call twice.

A paid judge makes thousands of calls. If the run dies at ninety percent,
the next run with the same cache file only makes the calls that are missing.

A cached verdict is only right while the grader is the same, so the key
includes a fingerprint of the grader: the bytes of its source file, or the
command line. A grader that changed gets no hits. That fingerprint cannot
see a prompt kept in another file or a model that moved behind the same
name, so delete the cache when either changes.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
from collections.abc import Callable
from pathlib import Path

from .model import Control, Item, Verdict


def fingerprint(grader_spec: str | None, command: str | None, pass_score: float) -> str:
    """What identifies this grader: its source file's bytes, or its command."""
    digest = hashlib.sha256()
    digest.update(f"pass_score={pass_score}\x1f".encode())
    if grader_spec:
        target, _, name = grader_spec.rpartition(":")
        digest.update(name.encode())
        digest.update(_source_bytes(target))
    if command:
        digest.update(command.encode())
    return digest.hexdigest()[:16]


def _source_bytes(target: str) -> bytes:
    """The bytes of the grader's source, for a file path or a module name."""
    path = Path(target)
    if path.is_file():
        return path.read_bytes()
    try:
        spec = importlib.util.find_spec(target)
    except (ImportError, ValueError):
        spec = None
    if spec is not None and spec.origin and Path(spec.origin).is_file():
        return Path(spec.origin).read_bytes()
    return target.encode()


class Cache:
    """An append-only JSON Lines file of verdicts, safe to use from many threads."""

    def __init__(self, path: str | Path, grader_fingerprint: str) -> None:
        self.path = Path(path)
        self.fingerprint = grader_fingerprint
        self.hits = 0
        self._lock = threading.Lock()
        self._seen: dict[str, Verdict] = {}
        self._asking: dict[str, threading.Event] = {}
        if self.path.exists():
            with open(self.path, encoding="utf-8") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                        self._seen[row["key"]] = Verdict.from_dict(row["verdict"])
                    except (ValueError, KeyError, TypeError, AttributeError):
                        continue  # a line cut off by a crash; the call is simply made again

    def key(self, item: Item, control: Control, trial: int) -> str:
        parts = [self.fingerprint, json.dumps(item.to_dict(), sort_keys=True), control.answer]
        digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()
        return f"{digest}:{trial}"

    def get(self, key: str) -> Verdict | None:
        with self._lock:
            found = self._seen.get(key)
            if found is not None:
                self.hits += 1
            return found

    def put(self, key: str, verdict: Verdict) -> None:
        if verdict.passed is None:
            return  # an error is not a verdict; the call is made again next time
        with self._lock:
            self._seen[key] = verdict
            with open(self.path, "a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps({"key": key, "verdict": verdict.to_dict()}) + "\n")

    def get_or_ask(self, key: str, ask: Callable[[], Verdict]) -> Verdict:
        """The cached verdict for `key`, or the result of `ask`, called at most once at a time.

        Two controls can be the same answer, and two workers can reach them in
        the same moment. Both would miss the cache and both would call the
        grader. The second one waits for the first instead, and takes its
        verdict. If the first got no verdict, the second asks for itself.
        """
        while True:
            with self._lock:
                found = self._seen.get(key)
                if found is not None:
                    self.hits += 1
                    return found
                waiting = self._asking.get(key)
                if waiting is None:
                    mine = self._asking[key] = threading.Event()
                    break
            waiting.wait()
        try:
            verdict = ask()
            self.put(key, verdict)
            return verdict
        finally:
            with self._lock:
                del self._asking[key]
            mine.set()
