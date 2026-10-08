"""Database models. Money is NUMERIC(18,2), FX rates NUMERIC(18,6): never floats."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Money = Numeric(18, 2)
Rate = Numeric(18, 6)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(StrEnum):
    ADMIN = "admin"  # HR admin: everything, including who can log in
    ACCOUNTANT = "accountant"  # HR / payroll: employees, compute & finalize payroll
    VIEWER = "viewer"  # auditor: reads every salary, changes nothing
    EMPLOYEE = "employee"  # self-service: only their own finalized pay


class RunStatus(StrEnum):
    DRAFT = "draft"
    FINALIZED = "finalized"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    memberships: Mapped[list[Membership]] = relationship(back_populates="user")


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    pan: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "company_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=20))
    # The employee record this login belongs to: required for EMPLOYEE, optional for HR staff
    # who are also on the payroll (gives them "My pay").
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), unique=True)
    user: Mapped[User] = relationship(back_populates="memberships")
    company: Mapped[Company] = relationship()
    employee: Mapped[Employee | None] = relationship()


class Invite(Base):
    """A one-time link that lets someone set their own password and join a company."""

    __tablename__ = "invites"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=20))
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256; the token itself is never stored
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    company: Mapped[Company] = relationship()
    employee: Mapped[Employee | None] = relationship()


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("company_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    pan: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    joined_on: Mapped[date] = mapped_column(Date)
    left_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    tax_profiles: Mapped[list[TaxProfile]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    salary_structures: Mapped[list[SalaryStructure]] = relationship(
        back_populates="employee", cascade="all, delete-orphan", order_by="SalaryStructure.effective_from"
    )


class TaxProfile(Base):
    """Per-employee, per-fiscal-year tax facts and declared reliefs (with proof on file)."""

    __tablename__ = "tax_profiles"
    __table_args__ = (UniqueConstraint("employee_id", "fiscal_year"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    fiscal_year: Mapped[str] = mapped_column(String(7))  # "2083/84"
    resident: Mapped[bool] = mapped_column(Boolean, default=True)
    filing: Mapped[str] = mapped_column(String(10), default="single")
    gender: Mapped[str] = mapped_column(String(10), default="male")
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ssf_enrolled: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_pension: Mapped[bool] = mapped_column(Boolean, default=False)
    remote_area: Mapped[str | None] = mapped_column(String(1))
    income_only_from_employment: Mapped[bool] = mapped_column(Boolean, default=True)
    life_insurance_premium: Mapped[Decimal] = mapped_column(Money, default=0)
    health_insurance_premium: Mapped[Decimal] = mapped_column(Money, default=0)
    building_insurance_premium: Mapped[Decimal] = mapped_column(Money, default=0)
    donation: Mapped[Decimal] = mapped_column(Money, default=0)
    employee: Mapped[Employee] = relationship(back_populates="tax_profiles")


class SalaryStructure(Base):
    """Recurring monthly pay from `effective_from` until the next structure starts."""

    __tablename__ = "salary_structures"
    __table_args__ = (UniqueConstraint("employee_id", "effective_from"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    effective_from: Mapped[date] = mapped_column(Date)
    # [{"kind": "basic", "amount": "1500.00", "currency": "USD", "description": ""}]
    components: Mapped[list] = mapped_column(JSON)
    cit_monthly: Mapped[Decimal] = mapped_column(Money, default=0)
    other_retirement_monthly: Mapped[Decimal] = mapped_column(Money, default=0)
    employee: Mapped[Employee] = relationship(back_populates="salary_structures")


class FxRateRow(Base):
    """Official NRB rates (company_id NULL, shared) and per-company overrides (bank credit rate)."""

    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("currency", "on", "source", "company_id", postgresql_nulls_not_distinct=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    currency: Mapped[str] = mapped_column(String(3), index=True)
    on: Mapped[date] = mapped_column(Date, index=True)
    buy: Mapped[Decimal] = mapped_column(Rate)
    sell: Mapped[Decimal] = mapped_column(Rate)
    unit: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(20))  # "NRB" | "OVERRIDE"
    override_reason: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PayrollRun(Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (UniqueConstraint("company_id", "fiscal_year", "month"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    fiscal_year: Mapped[str] = mapped_column(String(7))
    month: Mapped[int] = mapped_column(Integer)  # 1 = Shrawan … 12 = Ashadh
    payment_date: Mapped[date] = mapped_column(Date)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus, native_enum=False, length=20), default=RunStatus.DRAFT)
    rule_set: Mapped[str | None] = mapped_column(String(40))
    rule_review_status: Mapped[str | None] = mapped_column(String(20))
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    acknowledged_unverified: Mapped[list] = mapped_column(JSON, default=list)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    finalized_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payslips: Mapped[list[Payslip]] = relationship(back_populates="run", cascade="all, delete-orphan")
    adjustments: Mapped[list[RunAdjustment]] = relationship(back_populates="run", cascade="all, delete-orphan")


class RunAdjustment(Base):
    """One-off income for one employee in one run (bonus, Dashain allowance, arrears…)."""

    __tablename__ = "run_adjustments"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3), default="NPR")
    description: Mapped[str] = mapped_column(String(200), default="")
    run: Mapped[PayrollRun] = relationship(back_populates="adjustments")


class Payslip(Base):
    """Engine output for one employee in one run. Frozen once the run is finalized."""

    __tablename__ = "payslips"
    __table_args__ = (UniqueConstraint("run_id", "employee_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    month: Mapped[int] = mapped_column(Integer)
    gross: Mapped[Decimal] = mapped_column(Money)
    basic: Mapped[Decimal] = mapped_column(Money)
    recurring_income: Mapped[Decimal] = mapped_column(Money)
    recurring_basic: Mapped[Decimal] = mapped_column(Money)
    ssf_employee: Mapped[Decimal] = mapped_column(Money)
    ssf_employer: Mapped[Decimal] = mapped_column(Money)
    cit: Mapped[Decimal] = mapped_column(Money)
    other_retirement: Mapped[Decimal] = mapped_column(Money)
    tds: Mapped[Decimal] = mapped_column(Money)
    net_pay: Mapped[Decimal] = mapped_column(Money)
    projected_annual_tax: Mapped[Decimal] = mapped_column(Money)
    projected_taxable_income: Mapped[Decimal] = mapped_column(Money)
    inputs: Mapped[dict] = mapped_column(JSON)  # lines, FX rates used, profile snapshot
    trace: Mapped[list] = mapped_column(JSON)
    run: Mapped[PayrollRun] = relationship(back_populates="payslips")
    employee: Mapped[Employee] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
