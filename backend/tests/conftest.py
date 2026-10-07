from pathlib import Path

import pytest

from app.engine.rules import RULES_DIR, load_rule_file


@pytest.fixture(scope="session")
def rules_by_fy():
    return {p.stem: load_rule_file(p) for p in (RULES_DIR / "np").glob("*.yaml")}


@pytest.fixture(scope="session")
def fy8384(rules_by_fy):
    return rules_by_fy["2083-84"]


GOLDEN_DIR = Path(__file__).parent / "golden"
