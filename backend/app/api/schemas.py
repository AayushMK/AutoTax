"""API request/response models. Money is Decimal and serializes as a string (no float rounding)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import Role, RunStatus

Kind = Literal["basic", "allowance", "bonus", "dashain", "overtime", "benefit", "other"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth ---
class SignupIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1)
    password: str = Field(min_length=8)
    company_name: str = Field(min_length=1)
    company_pan: str | None = None
    pay_calendar: Literal["bs", "ad"] = "bs"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    token: str


class MembershipOut(ORM):
    company_id: int
    company_name: str
    role: Role
    employee_id: int | None = None


class MeOut(BaseModel):
    id: int
    email: str
    name: str
    memberships: list[MembershipOut]


# --- companies ---
class CompanyIn(BaseModel):
    name: str = Field(min_length=1)
    pan: str | None = None
    pay_calendar: Literal["bs", "ad"] = "bs"


class CompanyOut(ORM):
    id: int
    name: str
    pan: str | None
    pay_calendar: str


class PeriodOut(BaseModel):
    index: int
    label: str
    start: date
    end: date
    run_id: int | None = None
    status: RunStatus | None = None
    source: str | None = None


class MemberIn(BaseModel):
    email: EmailStr
    role: Role


class MemberOut(BaseModel):
    user_id: int
    email: str
    name: str
    role: Role
    employee_id: int | None = None
    employee_name: str | None = None


class InviteIn(BaseModel):
    email: EmailStr
    role: Role
    employee_id: int | None = None


class InviteOut(BaseModel):
    id: int
    email: str
    role: Role
    employee_id: int | None
    employee_name: str | None
    expires_at: datetime
    token: str | None = None  # only returned once, when the invite is created


class InviteInfo(BaseModel):
    company_id: int
    company_name: str
    email: str
    role: Role
    employee_name: str | None
    has_account: bool


class AcceptInviteIn(BaseModel):
    name: str = Field(default="", max_length=200)
    password: str = Field(min_length=8)


# --- employees ---
class EmployeeIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1)
    pan: str | None = None
    email: EmailStr | None = None
    joined_on: date
    left_on: date | None = None


class EmployeeOut(ORM):
    id: int
    code: str
    name: str
    pan: str | None
    email: str | None
    joined_on: date
    left_on: date | None


class TaxProfileIn(BaseModel):
    resident: bool = True
    filing: Literal["single", "couple"] = "single"
    gender: Literal["male", "female", "other"] = "male"
    disabled: bool = False
    ssf_enrolled: bool = False
    approved_pension: bool = False
    remote_area: Literal["A", "B", "C", "D", "E"] | None = None
    income_only_from_employment: bool = True
    prior_income: Decimal = Field(default=Decimal(0), ge=0)
    prior_retirement: Decimal = Field(default=Decimal(0), ge=0)
    prior_tds: Decimal = Field(default=Decimal(0), ge=0)
    life_insurance_premium: Decimal = Field(default=Decimal(0), ge=0)
    health_insurance_premium: Decimal = Field(default=Decimal(0), ge=0)
    building_insurance_premium: Decimal = Field(default=Decimal(0), ge=0)
    donation: Decimal = Field(default=Decimal(0), ge=0)


class TaxProfileOut(TaxProfileIn, ORM):
    fiscal_year: str


class Component(BaseModel):
    kind: Kind
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="NPR", min_length=3, max_length=3)
    description: str = ""

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class SalaryStructureIn(BaseModel):
    effective_from: date
    components: list[Component] = Field(min_length=1)
    cit_mode: Literal["fixed", "fill_cap"] = "fixed"
    cit_monthly: Decimal = Field(default=Decimal(0), ge=0)
    other_retirement_monthly: Decimal = Field(default=Decimal(0), ge=0)


class SalaryStructureOut(ORM):
    id: int
    effective_from: date
    components: list[Component]
    cit_mode: str
    cit_monthly: Decimal
    other_retirement_monthly: Decimal


class EmployeeDetail(EmployeeOut):
    tax_profiles: list[TaxProfileOut]
    salary_structures: list[SalaryStructureOut]


# --- payroll ---
class RunIn(BaseModel):
    payment_date: date
    # Required for English-month payroll (July belongs to two fiscal years); optional otherwise.
    fiscal_year: str | None = None
    period: int | None = Field(default=None, ge=1, le=13)


class ImportRow(BaseModel):
    employee_id: int
    gross: Decimal = Field(ge=0)
    basic: Decimal | None = Field(default=None, ge=0)
    ssf_total: Decimal | None = Field(default=None, ge=0)
    ssf_employee: Decimal | None = Field(default=None, ge=0)
    ssf_employer: Decimal | None = Field(default=None, ge=0)
    cit: Decimal = Field(default=Decimal(0), ge=0)
    other_retirement: Decimal = Field(default=Decimal(0), ge=0)
    tds: Decimal = Field(default=Decimal(0), ge=0)


class ImportIn(BaseModel):
    gross_includes_employer_ssf: bool = True
    rows: list[ImportRow] = Field(min_length=1)


class AdjustmentIn(BaseModel):
    employee_id: int
    kind: Kind = "bonus"
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="NPR", min_length=3, max_length=3)
    description: str = ""


class AdjustmentOut(ORM):
    id: int
    employee_id: int
    kind: str
    amount: Decimal
    currency: str
    description: str


class FinalizeIn(BaseModel):
    acknowledge_unverified: bool = False


class PayslipSummary(ORM):
    id: int
    employee_id: int
    employee_code: str
    employee_name: str
    gross: Decimal
    ssf_employee: Decimal
    ssf_employer: Decimal
    cit: Decimal
    tds: Decimal
    net_pay: Decimal
    projected_annual_tax: Decimal
    share: str | None = None  # e.g. "15/31" when only part of the month is paid
    projected_tax_without_cit: Decimal = Decimal(0)


class PayslipDetail(PayslipSummary):
    month: int
    basic: Decimal
    other_retirement: Decimal
    projected_taxable_income: Decimal
    inputs: dict
    trace: list[dict]


class Totals(BaseModel):
    gross: Decimal
    ssf_employee: Decimal
    ssf_employer: Decimal
    cit: Decimal
    tds: Decimal
    net_pay: Decimal


class RunOut(ORM):
    id: int
    fiscal_year: str
    month: int
    month_label: str
    period_start: date
    period_end: date
    payment_date: date
    status: RunStatus
    source: str
    rule_set: str | None
    rule_review_status: str | None
    warnings: list[str]
    acknowledged_unverified: list[str]
    computed_at: datetime | None
    finalized_at: datetime | None


class RunDetail(RunOut):
    payslips: list[PayslipSummary]
    adjustments: list[AdjustmentOut]
    totals: Totals


# --- fx ---
class FxOverrideIn(BaseModel):
    currency: str = Field(min_length=3, max_length=3)
    on: date
    buy: Decimal = Field(gt=0)
    sell: Decimal = Field(gt=0)
    unit: int = Field(default=1, gt=0)
    reason: str = Field(min_length=3)


class FxSyncIn(BaseModel):
    start: date
    end: date
    currencies: list[str] | None = None


class FxRateOut(ORM):
    currency: str
    on: date
    buy: Decimal
    sell: Decimal
    unit: int
    source: str
    override_reason: str | None


class AuditOut(ORM):
    id: int
    user_id: int | None
    action: str
    entity: str
    entity_id: int | None
    data: dict
    at: datetime

