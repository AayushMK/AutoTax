import pytest
import yaml

from app.engine import AnnualFigures, AnnualReliefs, EmployeeProfile, compute_annual_tax
from app.engine.money import D

from .conftest import GOLDEN_DIR

CASES = yaml.safe_load((GOLDEN_DIR / "annual_cases.yaml").read_text())


def _decimals(d: dict | None) -> dict:
    return {k: D(v) for k, v in (d or {}).items()}


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_golden(case, rules_by_fy):
    rules = rules_by_fy[case["rules"]]
    profile = EmployeeProfile(employee_id="t", **case.get("profile", {}))
    result = compute_annual_tax(
        profile,
        AnnualFigures(**_decimals(case["figures"])),
        AnnualReliefs(**_decimals(case.get("reliefs"))),
        rules,
    )
    for field, expected in case["expect"].items():
        assert getattr(result, field) == D(expected), f"{field}\n{result.trace}"


def test_trace_cites_rule_file(fy8384):
    r = compute_annual_tax(
        EmployeeProfile("t", ssf_enrolled=True),
        AnnualFigures(gross_income=D(1500000), basic=D(1200000), ssf_employee=D(132000), ssf_employer=D(240000)),
        AnnualReliefs(),
        fy8384,
    )
    text = str(r.trace)
    assert "Sec 63(1)" in text and "SST waived" in text
    assert r.rule_set == "NP/2083/84/v1"
