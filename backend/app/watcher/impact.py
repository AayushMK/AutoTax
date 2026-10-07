"""Show what a proposed rule change does to tax, using the golden cases as sample employees."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml

from app.engine import AnnualFigures, AnnualReliefs, EmployeeProfile, compute_annual_tax
from app.engine.money import D
from app.engine.rules import RuleSet

GOLDEN = Path(__file__).resolve().parents[2] / "tests" / "golden" / "annual_cases.yaml"


@dataclass(frozen=True)
class ImpactRow:
    case: str
    before: Decimal
    after: Decimal

    @property
    def delta(self) -> Decimal:
        return self.after - self.before


def impact(before: RuleSet, after: RuleSet, golden: Path = GOLDEN) -> list[ImpactRow]:
    rows = []
    for case in yaml.safe_load(golden.read_text(encoding="utf-8")):
        profile = EmployeeProfile(employee_id="sample", **case.get("profile", {}))
        figures = AnnualFigures(**{k: D(v) for k, v in case["figures"].items()})
        reliefs = AnnualReliefs(**{k: D(v) for k, v in (case.get("reliefs") or {}).items()})
        b = compute_annual_tax(profile, figures, reliefs, before).total_tax
        a = compute_annual_tax(profile, figures, reliefs, after).total_tax
        rows.append(ImpactRow(case["name"], b, a))
    return rows
