"""Payroll run lifecycle: create → (adjust) → compute → finalize.

- compute: runs the engine for every employee in service that month and stores draft payslips.
  All-or-nothing: if any employee has a problem the run is not computed and every problem is listed.
- finalize: recomputes from current inputs, re-checks the rule gate (unverified rules need an
  explicit acknowledgement, which is recorded), then freezes the run. Finalized runs never change;
  their payslips are the history later months build on.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine import (
    AnnualReliefs,
    EmployeeProfile,
    FxRateMissing,
    IncomeKind,
    IncomeLine,
    MonthInput,
    PayrollSequenceError,
    PostedMonth,
    compute_month,
)
from app.engine.gate import (
    RuleCoverageError,
    SourceIntegrityError,
    UnverifiedRulesError,
    check_payroll_allowed,
)
from app.engine.money import D
from app.engine.trace import Trace
from app.models import Employee, Payslip, PayrollRun, RunAdjustment, RunStatus, SalaryStructure, TaxProfile

from . import audit, fx_store
from .calendar import fiscal_year_of, fy_bounds, fy_month, service_months


class PayrollError(Exception):
    def __init__(self, message: str, problems: list[str] | None = None):
        super().__init__(message)
        self.problems = problems or []


class RulesNotAcknowledged(PayrollError):
    def __init__(self, err: UnverifiedRulesError):
        super().__init__(str(err), err.params)
        self.rule_set = err.rule_set.version_id


def create_run(db: Session, company_id: int, payment_date: date, user_id: int) -> PayrollRun:
    fy, month = fiscal_year_of(payment_date), fy_month(payment_date)
    if db.scalar(select(PayrollRun).where(PayrollRun.company_id == company_id, PayrollRun.fiscal_year == fy, PayrollRun.month == month)):
        raise PayrollError(f"a payroll run for {fy} month {month} already exists")
    run = PayrollRun(company_id=company_id, fiscal_year=fy, month=month, payment_date=payment_date, created_by=user_id,
                     warnings=[], acknowledged_unverified=[])
    db.add(run)
    db.flush()
    audit.record(db, company_id=company_id, user_id=user_id, action="payroll.create", entity="payroll_run",
                 entity_id=run.id, data={"fiscal_year": fy, "month": month, "payment_date": payment_date})
    return run


def compute_run(db: Session, run: PayrollRun, user_id: int) -> PayrollRun:
    _require_draft(run)
    gate = _gate(run.payment_date, acknowledge=True)
    rules = gate.rule_set
    if rules.fiscal_year != run.fiscal_year:
        raise PayrollError(f"rule set {rules.version_id} does not match run fiscal year {run.fiscal_year}")

    employees = _employees_in_service(db, run)
    adjustments: dict[int, list[RunAdjustment]] = {}
    for a in run.adjustments:
        adjustments.setdefault(a.employee_id, []).append(a)

    currencies = {c["currency"] for e in employees for s in e.salary_structures for c in s.components}
    currencies |= {a.currency for a in run.adjustments}
    fx = fx_store.table_for(db, run.company_id, currencies, run.payment_date)

    run.payslips.clear()
    db.flush()
    problems: list[str] = []
    for emp in employees:
        try:
            run.payslips.append(_compute_employee(db, run, emp, adjustments.get(emp.id, []), rules, fx))
        except (PayrollError, PayrollSequenceError, FxRateMissing, ValueError) as e:
            problems.append(f"{emp.code} {emp.name}: {e}")
    if problems:
        db.rollback()
        raise PayrollError(f"{len(problems)} employee(s) could not be computed", problems)
    if not employees:
        raise PayrollError("no employees are in service for this month")

    run.rule_set = rules.version_id
    run.rule_review_status = rules.raw.review.status
    run.warnings = gate.warnings
    run.computed_at = datetime.now(timezone.utc)
    audit.record(db, company_id=run.company_id, user_id=user_id, action="payroll.compute", entity="payroll_run",
                 entity_id=run.id, data={"rule_set": rules.version_id, "employees": len(employees),
                                         "total_tds": sum((p.tds for p in run.payslips), Decimal(0))})
    return run


def finalize_run(db: Session, run: PayrollRun, user_id: int, acknowledge_unverified: bool) -> PayrollRun:
    _require_draft(run)
    try:
        gate = check_payroll_allowed(run.payment_date, acknowledge_unverified=acknowledge_unverified)
    except UnverifiedRulesError as e:
        raise RulesNotAcknowledged(e) from e
    except (RuleCoverageError, SourceIntegrityError) as e:
        raise PayrollError(str(e)) from e
    earlier_draft = db.scalar(select(PayrollRun).where(
        PayrollRun.company_id == run.company_id, PayrollRun.fiscal_year == run.fiscal_year,
        PayrollRun.month < run.month, PayrollRun.status == RunStatus.DRAFT,
    ))
    if earlier_draft:
        raise PayrollError(f"finalize month {earlier_draft.month} first")
    compute_run(db, run, user_id)  # always finalize what the current inputs produce
    run.status = RunStatus.FINALIZED
    run.finalized_by = user_id
    run.finalized_at = datetime.now(timezone.utc)
    run.acknowledged_unverified = gate.acknowledged_unverified
    audit.record(db, company_id=run.company_id, user_id=user_id, action="payroll.finalize", entity="payroll_run",
                 entity_id=run.id, data={"rule_set": run.rule_set, "acknowledged_unverified": gate.acknowledged_unverified,
                                         "total_tds": sum((p.tds for p in run.payslips), Decimal(0))})
    return run


# --- internals -------------------------------------------------------------------------------

def _gate(on: date, acknowledge: bool):
    try:
        return check_payroll_allowed(on, acknowledge_unverified=acknowledge)
    except (RuleCoverageError, SourceIntegrityError) as e:
        raise PayrollError(str(e)) from e


def _require_draft(run: PayrollRun) -> None:
    if run.status != RunStatus.DRAFT:
        raise PayrollError("this payroll run is finalized and cannot change")


def _employees_in_service(db: Session, run: PayrollRun) -> list[Employee]:
    start, end = fy_bounds(run.fiscal_year)
    emps = db.scalars(select(Employee).where(
        Employee.company_id == run.company_id, Employee.joined_on <= end,
        (Employee.left_on.is_(None)) | (Employee.left_on >= start),
    ).order_by(Employee.code)).all()
    out = []
    for e in emps:
        months = service_months(run.fiscal_year, e.joined_on, e.left_on)
        if months and months[0] <= run.month <= months[1]:
            out.append(e)
    return out


def _compute_employee(db, run, emp, adjustments, rules, fx) -> Payslip:
    first, last = service_months(run.fiscal_year, emp.joined_on, emp.left_on)
    tp = db.scalar(select(TaxProfile).where(TaxProfile.employee_id == emp.id, TaxProfile.fiscal_year == run.fiscal_year))
    if tp is None:
        raise PayrollError(f"no tax profile for {run.fiscal_year}")
    structure = _structure_on(emp, run.payment_date)
    if structure is None:
        raise PayrollError(f"no salary structure effective on {run.payment_date}")

    history = [_posted(p) for p in db.scalars(
        select(Payslip).join(PayrollRun).where(
            Payslip.employee_id == emp.id, PayrollRun.fiscal_year == run.fiscal_year,
            PayrollRun.status == RunStatus.FINALIZED, Payslip.month < run.month,
        ).order_by(Payslip.month)
    )]
    expected = list(range(first, run.month))
    if [h.month for h in history] != expected:
        missing = sorted(set(expected) - {h.month for h in history})
        raise PayrollError(f"months {missing} of this fiscal year are not finalized yet")

    profile = EmployeeProfile(
        employee_id=emp.code, resident=tp.resident, filing=tp.filing, gender=tp.gender, disabled=tp.disabled,
        ssf_enrolled=tp.ssf_enrolled, approved_pension=tp.approved_pension, remote_area=tp.remote_area,
        income_only_from_employment=tp.income_only_from_employment, first_month=first, last_month=last,
    )
    reliefs = AnnualReliefs(
        life_insurance_premium=tp.life_insurance_premium, health_insurance_premium=tp.health_insurance_premium,
        building_insurance_premium=tp.building_insurance_premium, donation=tp.donation,
    )
    lines = [
        IncomeLine(IncomeKind(c["kind"]), D(c["amount"]), c.get("currency", "NPR"), run.payment_date, True, c.get("description", ""))
        for c in structure.components
    ] + [
        IncomeLine(IncomeKind(a.kind), a.amount, a.currency, run.payment_date, False, a.description)
        for a in adjustments
    ]
    month_input = MonthInput(month=run.month, lines=lines, cit=structure.cit_monthly, other_retirement=structure.other_retirement_monthly)
    res = compute_month(profile, reliefs, rules, history, month_input, fx)

    fx_used = {}
    for cur in {l.currency.upper() for l in lines} - {"NPR"}:
        r = fx.lookup(cur, run.payment_date)
        fx_used[cur] = {"on": str(r.on), "buy": str(r.buy), "sell": str(r.sell), "unit": r.unit,
                        "source": r.source, "override_reason": r.override_reason}
    pm = res.posted
    return Payslip(
        employee_id=emp.id, month=run.month, gross=pm.gross_income, basic=pm.basic,
        recurring_income=pm.recurring_income, recurring_basic=pm.recurring_basic,
        ssf_employee=pm.ssf_employee, ssf_employer=pm.ssf_employer, cit=pm.cit, other_retirement=pm.other_retirement,
        tds=res.tds, net_pay=res.net_pay, projected_annual_tax=res.annual.total_tax,
        projected_taxable_income=res.annual.taxable_income,
        inputs={
            "rule_set": rules.version_id,
            "profile": {k: v for k, v in asdict(profile).items()},
            "reliefs": {k: str(v) for k, v in asdict(reliefs).items()},
            "lines": [{"kind": str(l.kind), "amount": str(l.amount), "currency": l.currency, "recurring": l.recurring,
                       "description": l.description} for l in lines],
            "cit": str(structure.cit_monthly), "other_retirement": str(structure.other_retirement_monthly),
            "fx": fx_used,
            "structure_id": structure.id,
        },
        trace=trace_json(res.trace),
    )


def _structure_on(emp: Employee, on: date) -> SalaryStructure | None:
    valid = [s for s in emp.salary_structures if s.effective_from <= on]
    return max(valid, key=lambda s: s.effective_from) if valid else None


def _posted(p: Payslip) -> PostedMonth:
    return PostedMonth(
        month=p.month, gross_income=p.gross, basic=p.basic, recurring_income=p.recurring_income,
        recurring_basic=p.recurring_basic, ssf_employee=p.ssf_employee, ssf_employer=p.ssf_employer,
        cit=p.cit, other_retirement=p.other_retirement, tds=p.tds,
    )


def trace_json(t: Trace) -> list[dict]:
    return [
        {
            "label": s.label, "amount": str(s.amount), "detail": s.detail,
            "citation": None if s.citation is None else {
                "key": s.citation.key, "ref": s.citation.ref, "source": s.citation.source_title, "status": s.citation.status,
            },
        }
        for s in t.steps
    ]
