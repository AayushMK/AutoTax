"""Pure tax engine: rule files in, numbers + trace out. No I/O beyond loading rule files."""

from .annual import compute_annual_tax
from .fx import FxRate, FxRateMissing, FxTable
from .models import (
    AnnualFigures,
    AnnualReliefs,
    AnnualTaxResult,
    EmployeeProfile,
    IncomeKind,
    IncomeLine,
    MonthInput,
    MonthResult,
    PostedMonth,
    PriorEmployment,
)
from .rules import RuleFileError, RuleSet, load_rule_file, rules_for_date
from .tds import PayrollSequenceError, compute_month

__all__ = [
    "AnnualFigures",
    "AnnualReliefs",
    "AnnualTaxResult",
    "EmployeeProfile",
    "FxRate",
    "FxRateMissing",
    "FxTable",
    "IncomeKind",
    "IncomeLine",
    "MonthInput",
    "MonthResult",
    "PayrollSequenceError",
    "PostedMonth",
    "PriorEmployment",
    "RuleFileError",
    "RuleSet",
    "compute_annual_tax",
    "compute_month",
    "load_rule_file",
    "rules_for_date",
]
