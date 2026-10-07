import os

# Tests use their own database and never call NRB live; set before app.db is imported.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://autotax:autotax@localhost:5434/autotax_test")
os.environ["FETCH_FX"] = "0"

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
