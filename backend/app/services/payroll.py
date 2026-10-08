"""Payroll run lifecycle: create → (adjust | import) → compute → finalize.

- A run is one pay period of the company's calendar: a Nepali month, or an English month
  (with July split between fiscal years). Rules come from the period's end date, FX from the
  payment date.
- compute: runs the engine for every employee in service in the period and stores draft payslips.
  Pay is prorated by days for split periods and mid-period joiners/leavers. All-or-nothing: if any
  employee has a problem the run is not computed and every problem is listed.
- import: for periods paid before the company used the app, HR enters each employee's figures;
  they become history that later periods build on (e.g. TDS not withheld in the first months).
- finalize: recomputes from current inputs (computed runs), re-checks the rule gate (unverified
  rules need an explicit, recorded acknowledgement), then freezes the run for good.
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
    PriorEmployment,
    compute_month,
)
from app.engine.gate import (
    RuleCoverageError,
    SourceIntegrityError,
    UnverifiedRulesError,
    check_payroll_allowed,
)
from app.engine.money import D, ZERO, round_money
from app.engine.trace import Trace
from app.models import Company, Employee, Payslip, PayrollRun, RunAdjustment, RunStatus, SalaryStructure, TaxProfile

from . import audit, fx_store
from .calendar import Period, fy_bounds, period, period_of, periods, service_periods, share

COMPUTED, IMPORTED = "computed", "imported"


class PayrollError(Exception):
    def __init__(self, message: str, problems: list[str] | None = None):
        super().__init__(message)
        self.problems = problems or []


class RulesNotAcknowledged(PayrollError):
    def __init__(self, err: UnverifiedRulesError):
        super().__init__(str(err), err.params)
        self.rule_set = err.rule_set.version_id


def run_period(db: Session, run: PayrollRun) -> Period:
    return period(run.fiscal_year, run.month, db.get(Company, run.company_id).pay_calendar)


def create_run(db: Session, company: Company, payment_date: date, user_id: int,
               fiscal_year: str | None = None, period_index: int | None = None) -> PayrollRun:
    if fiscal_year and period_index:
        try:
            p = period(fiscal_year, period_index, company.pay_calendar)
        except ValueError as e:
            raise PayrollError(str(e)) from e
    elif company.pay_calendar == "ad":
        raise PayrollError("choose the pay period: with English-month payroll July belongs to two fiscal years")
    else:
        p = period_of(payment_date, "bs")
    if payment_date < p.start:
        raise PayrollError(f"the payment date is before {p.label} starts ({p.start})")
    if db.scalar(select(PayrollRun).where(PayrollRun.company_id == company.id, PayrollRun.fiscal_year == p.fiscal_year,
                                          PayrollRun.month == p.index)):
        raise PayrollError(f"payroll for {p.label} (FY {p.fiscal_year}) already exists")
    run = PayrollRun(company_id=company.id, fiscal_year=p.fiscal_year, month=p.index, payment_date=payment_date,
                     created_by=user_id, warnings=[], acknowledged_unverified=[], source=COMPUTED)
    db.add(run)
    db.flush()
    audit.record(db, company_id=company.id, user_id=user_id, action="payroll.create", entity="payroll_run",
                 entity_id=run.id, data={"fiscal_year": p.fiscal_year, "period": p.label, "payment_date": payment_date})
    return run


def compute_run(db: Session, run: PayrollRun, user_id: int) -> PayrollRun:
    _require_draft(run)
    if run.source == IMPORTED:
        raise PayrollError("this month holds imported figures; edit them instead of calculating")
    company = db.get(Company, run.company_id)
    p = run_period(db, run)
    gate = _gate(p.end, acknowledge=True)
    rules = gate.rule_set
    if rules.fiscal_year != run.fiscal_year:
        raise PayrollError(f"rule set {rules.version_id} does not match run fiscal year {run.fiscal_year}")

    employees = _employees_in_service(db, run, company.pay_calendar)
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
            run.payslips.append(_compute_employee(db, run, company.pay_calendar, emp, adjustments.get(emp.id, []), rules, fx))
        except (PayrollError, PayrollSequenceError, FxRateMissing, ValueError) as e:
            problems.append(f"{emp.code} {emp.name}: {e}")
    if problems:
        db.rollback()
        raise PayrollError(f"{len(problems)} employee(s) could not be computed", problems)
    if not employees:
        raise PayrollError(f"no employees are in service in {p.label}")

    run.rule_set = rules.version_id
    run.rule_review_status = rules.raw.review.status
    run.warnings = gate.warnings
    run.computed_at = datetime.now(timezone.utc)
    audit.record(db, company_id=run.company_id, user_id=user_id, action="payroll.compute", entity="payroll_run",
                 entity_id=run.id, data={"rule_set": rules.version_id, "employees": len(employees),
                                         "total_tds": sum((s.tds for s in run.payslips), Decimal(0))})
    return run


def import_run(db: Session, run: PayrollRun, rows: list[dict], gross_includes_employer_ssf: bool, user_id: int) -> PayrollRun:
    """Replace a draft run's payslips with figures from payroll done outside the app.

    Each row: employee_id, gross, cit, tds, and either ssf_total (split 11:20) or ssf_employee and
    ssf_employer; optional basic and other_retirement. If gross_includes_employer_ssf (gross as
    cost-to-company), the employer's SSF is taken out of gross, since the app adds it separately.
    """
    _require_draft(run)
    company_emps = {e.id: e for e in db.scalars(select(Employee).where(Employee.company_id == run.company_id))}
    problems, slips = [], []
    seen: set[int] = set()
    for i, r in enumerate(rows, start=1):
        emp = company_emps.get(int(r.get("employee_id", 0)))
        if emp is None:
            problems.append(f"row {i}: unknown employee")
            continue
        if emp.id in seen:
            problems.append(f"row {i}: {emp.code} appears twice")
            continue
        seen.add(emp.id)
        try:
            amt = lambda k: round_money(D(r.get(k) or 0))  # noqa: E731  (paisa, like everything stored)
            gross, cit, tds, other = amt("gross"), amt("cit"), amt("tds"), amt("other_retirement")
            if r.get("ssf_total") not in (None, ""):
                total = amt("ssf_total")
                ssf_er = round_money(total * 20 / 31)
                ssf_ee = total - ssf_er
            else:
                ssf_ee, ssf_er = amt("ssf_employee"), amt("ssf_employer")
        except Exception:
            problems.append(f"row {i} ({emp.code}): amounts must be numbers")
            continue
        if gross_includes_employer_ssf:
            gross -= ssf_er
        if min(gross, cit, tds, ssf_ee, ssf_er, other) < 0:
            problems.append(f"row {i} ({emp.code}): amounts can't be negative")
            continue
        net = gross - ssf_ee - cit - other - tds
        slips.append(Payslip(
            employee_id=emp.id, month=run.month, gross=gross, basic=amt("basic"), recurring_income=ZERO,
            recurring_basic=ZERO, ssf_employee=ssf_ee, ssf_employer=ssf_er, cit=cit, other_retirement=other, tds=tds,
            net_pay=net, projected_annual_tax=ZERO, projected_taxable_income=ZERO,
            inputs={"imported": True, "gross_includes_employer_ssf": gross_includes_employer_ssf, "row": {k: str(v) for k, v in r.items()},
                    "lines": [], "fx": {}, "rule_set": None},
            trace=[{"label": "Imported from payroll done outside AutoTax", "amount": str(gross),
                    "detail": f"gross {gross} (excl. employer SSF), SSF {ssf_ee} + {ssf_er}, CIT {cit}, TDS {tds}", "citation": None}],
        ))
    if problems:
        raise PayrollError(f"{len(problems)} row(s) could not be imported", problems)
    run.payslips.clear()
    db.flush()
    run.payslips.extend(slips)
    run.source = IMPORTED
    run.computed_at = datetime.now(timezone.utc)
    run.rule_set = None
    audit.record(db, company_id=run.company_id, user_id=user_id, action="payroll.import", entity="payroll_run",
                 entity_id=run.id, data={"employees": len(slips), "gross_includes_employer_ssf": gross_includes_employer_ssf,
                                         "total_tds": sum((s.tds for s in slips), Decimal(0))})
    return run


def finalize_run(db: Session, run: PayrollRun, user_id: int, acknowledge_unverified: bool) -> PayrollRun:
    _require_draft(run)
    earlier_draft = db.scalar(select(PayrollRun).where(
        PayrollRun.company_id == run.company_id, PayrollRun.fiscal_year == run.fiscal_year,
        PayrollRun.month < run.month, PayrollRun.status == RunStatus.DRAFT,
    ))
    if earlier_draft:
        raise PayrollError(f"finalize {run_period(db, earlier_draft).label} first")
    acknowledged: list[str] = []
    if run.source == IMPORTED:
        if not run.payslips:
            raise PayrollError("enter the imported figures first")
    else:
        try:
            gate = check_payroll_allowed(run_period(db, run).end, acknowledge_unverified=acknowledge_unverified)
        except UnverifiedRulesError as e:
            raise RulesNotAcknowledged(e) from e
        except (RuleCoverageError, SourceIntegrityError) as e:
            raise PayrollError(str(e)) from e
        compute_run(db, run, user_id)  # always finalize what the current inputs produce
        acknowledged = gate.acknowledged_unverified
    run.status = RunStatus.FINALIZED
    run.finalized_by = user_id
    run.finalized_at = datetime.now(timezone.utc)
    run.acknowledged_unverified = acknowledged
    audit.record(db, company_id=run.company_id, user_id=user_id, action="payroll.finalize", entity="payroll_run",
                 entity_id=run.id, data={"rule_set": run.rule_set, "source": run.source, "acknowledged_unverified": acknowledged,
                                         "total_tds": sum((s.tds for s in run.payslips), Decimal(0))})
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


def _employees_in_service(db: Session, run: PayrollRun, cal: str) -> list[Employee]:
    start, end = fy_bounds(run.fiscal_year)
    emps = db.scalars(select(Employee).where(
        Employee.company_id == run.company_id, Employee.joined_on <= end,
        (Employee.left_on.is_(None)) | (Employee.left_on >= start),
    ).order_by(Employee.code)).all()
    out = []
    for e in emps:
        span = service_periods(run.fiscal_year, e.joined_on, e.left_on, cal)
        if span and span[0] <= run.month <= span[1]:
            out.append(e)
    return out


def _compute_employee(db, run, cal, emp, adjustments, rules, fx) -> Payslip:
    first, last = service_periods(run.fiscal_year, emp.joined_on, emp.left_on, cal)
    ps = periods(run.fiscal_year, cal)
    cur = ps[run.month - 1]
    tp = db.scalar(select(TaxProfile).where(TaxProfile.employee_id == emp.id, TaxProfile.fiscal_year == run.fiscal_year))
    if tp is None:
        raise PayrollError(f"no tax profile for {run.fiscal_year}")
    structure = _structure_on(emp, cur.end)
    if structure is None:
        raise PayrollError(f"no salary structure effective on {cur.end}")

    history = [_posted(p) for p in db.scalars(
        select(Payslip).join(PayrollRun).where(
            Payslip.employee_id == emp.id, PayrollRun.fiscal_year == run.fiscal_year,
            PayrollRun.status == RunStatus.FINALIZED, Payslip.month < run.month,
        ).order_by(Payslip.month)
    )]
    expected = list(range(first, run.month))
    if [h.month for h in history] != expected:
        missing = sorted(set(expected) - {h.month for h in history})
        raise PayrollError(f"{', '.join(ps[m - 1].label for m in missing)} not finalized yet")

    share_now = share(cur, emp.joined_on, emp.left_on)
    days = round(share_now * cur.month_days)
    remaining = tuple(share(q, emp.joined_on, emp.left_on) for q in ps[run.month:last])
    profile = EmployeeProfile(
        employee_id=emp.code, resident=tp.resident, filing=tp.filing, gender=tp.gender, disabled=tp.disabled,
        ssf_enrolled=tp.ssf_enrolled, approved_pension=tp.approved_pension, remote_area=tp.remote_area,
        income_only_from_employment=tp.income_only_from_employment, first_month=first, last_month=last,
    )
    reliefs = AnnualReliefs(
        life_insurance_premium=tp.life_insurance_premium, health_insurance_premium=tp.health_insurance_premium,
        building_insurance_premium=tp.building_insurance_premium, donation=tp.donation,
    )
    prior = PriorEmployment(income=tp.prior_income, retirement=tp.prior_retirement, tds=tp.prior_tds)
    lines = [
        IncomeLine(IncomeKind(c["kind"]), D(c["amount"]), c.get("currency", "NPR"), run.payment_date, True, c.get("description", ""))
        for c in structure.components
    ] + [
        IncomeLine(IncomeKind(a.kind), a.amount, a.currency, run.payment_date, False, a.description)
        for a in adjustments
    ]
    month_input = MonthInput(
        month=run.month, lines=lines, cit=structure.cit_monthly, other_retirement=structure.other_retirement_monthly,
        share=share_now, share_note=f"{days} of {cur.month_days} days", remaining_shares=remaining, cit_mode=structure.cit_mode,
    )
    res = compute_month(profile, reliefs, rules, history, month_input, fx, prior)

    fx_used = {}
    for c in {line.currency.upper() for line in lines} - {"NPR"}:
        r = fx.lookup(c, run.payment_date)
        fx_used[c] = {"on": str(r.on), "buy": str(r.buy), "sell": str(r.sell), "unit": r.unit,
                      "source": r.source, "override_reason": r.override_reason}
    pm = res.posted
    return Payslip(
        employee_id=emp.id, month=run.month, share_num=share_now.numerator, share_den=share_now.denominator,
        gross=pm.gross_income, basic=pm.basic, recurring_income=pm.recurring_income, recurring_basic=pm.recurring_basic,
        ssf_employee=pm.ssf_employee, ssf_employer=pm.ssf_employer, cit=pm.cit, other_retirement=pm.other_retirement,
        tds=res.tds, net_pay=res.net_pay, projected_annual_tax=res.annual.total_tax,
        projected_taxable_income=res.annual.taxable_income, projected_tax_without_cit=res.tax_without_cit,
        inputs={
            "rule_set": rules.version_id,
            "period": {"label": cur.label, "start": str(cur.start), "end": str(cur.end), "days_paid": days,
                       "month_days": cur.month_days},
            "profile": {k: v for k, v in asdict(profile).items()},
            "reliefs": {k: str(v) for k, v in asdict(reliefs).items()},
            "prior_employment": {k: str(v) for k, v in asdict(prior).items()},
            "lines": [{"kind": str(line.kind), "amount": str(line.amount), "currency": line.currency,
                       "recurring": line.recurring, "description": line.description} for line in lines],
            "cit_mode": structure.cit_mode, "cit_monthly": str(structure.cit_monthly),
            "other_retirement": str(structure.other_retirement_monthly),
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
