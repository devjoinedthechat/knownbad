from pathlib import Path

import pytest

from knownbad.io import read_items

EXAMPLE = Path(__file__).parent.parent / "examples" / "support"


@pytest.fixture(scope="session")
def items():
    return read_items(EXAMPLE / "items.jsonl")


@pytest.fixture(scope="session")
def items_path():
    return str(EXAMPLE / "items.jsonl")


@pytest.fixture(scope="session")
def graders_path():
    return str(EXAMPLE / "graders.py")
