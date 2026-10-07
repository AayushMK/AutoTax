"""Engine input/output types. Plain dataclasses: no I/O, no ORM."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from .money import ZERO
from .trace import Trace


class IncomeKind(StrEnum):
    BASIC = "basic"
    ALLOWANCE = "allowance"
    BONUS = "bonus"
    DASHAIN = "dashain"
    OVERTIME = "overtime"
    BENEFIT = "benefit"  # taxable perquisite (vehicle, housing) valued per IRD rules
    OTHER = "other"


@dataclass(frozen=True)
class IncomeLine:
    kind: IncomeKind
    amount: Decimal
    currency: str = "NPR"
    payment_date: date | None = None  # required for non-NPR lines (FX date basis)
    recurring: bool = True  # recurring lines are projected over remaining months
    description: str = ""


@dataclass(frozen=True)
class EmployeeProfile:
    employee_id: str
    resident: bool = True
    filing: Literal["single", "couple"] = "single"
    gender: Literal["male", "female", "other"] = "male"
    disabled: bool = False
    ssf_enrolled: bool = False
    approved_pension: bool = False  # contributes to an approved pension fund (SST waiver)
    remote_area: Literal["A", "B", "C", "D", "E"] | None = None
    income_only_from_employment: bool = True
    first_month: int = 1  # FY month index 1=Shrawan .. 12=Ashadh (mid-year joiners)
    last_month: int = 12  # mid-year leavers


@dataclass(frozen=True)
class AnnualReliefs:
    """Annual premium/donation amounts in NPR, declared by the employee with proof."""

    life_insurance_premium: Decimal = ZERO
    health_insurance_premium: Decimal = ZERO
    building_insurance_premium: Decimal = ZERO
    donation: Decimal = ZERO


@dataclass(frozen=True)
class AnnualFigures:
    """Annual totals in NPR (actual or projected) fed to the annual tax computation."""

    gross_income: Decimal  # cash + benefits, excluding employer SSF
    basic: Decimal
    ssf_employee: Decimal = ZERO
    ssf_employer: Decimal = ZERO
    cit: Decimal = ZERO
    other_retirement: Decimal = ZERO  # EPF / approved retirement funds


@dataclass
class AnnualTaxResult:
    assessable_income: Decimal
    retirement_deduction: Decimal
    remote_area_deduction: Decimal
    insurance_deduction: Decimal
    donation_deduction: Decimal
    taxable_income: Decimal
    sst: Decimal  # 1% social security tax portion
    income_tax: Decimal  # slab tax excluding SST
    rebate: Decimal
    total_tax: Decimal
    rule_set: str
    trace: Trace = field(default_factory=Trace)


@dataclass(frozen=True)
class MonthInput:
    month: int  # FY month index 1..12
    lines: list[IncomeLine]
    cit: Decimal = ZERO  # employee's CIT contribution this month (NPR)
    other_retirement: Decimal = ZERO
    retirement_recurring: bool = True


@dataclass(frozen=True)
class PostedMonth:
    """A finalized month, frozen in NPR. Stored verbatim; never recomputed."""

    month: int
    gross_income: Decimal
    basic: Decimal
    recurring_income: Decimal
    recurring_basic: Decimal
    ssf_employee: Decimal
    ssf_employer: Decimal
    cit: Decimal
    other_retirement: Decimal
    tds: Decimal


@dataclass
class MonthResult:
    posted: PostedMonth
    tds: Decimal
    net_pay: Decimal
    projected_annual: AnnualFigures
    annual: AnnualTaxResult
    trace: Trace
