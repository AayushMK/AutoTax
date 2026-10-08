"""Month-by-month and whole-year pay statements: SSF, CIT, TDS per employee and per company."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Employee, Payslip, PayrollRun, RunStatus

from .calendar import month_label

def money_json(v):
    """Decimals as strings, recursively. FastAPI would otherwise turn Decimals in plain dicts into floats."""
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, dict):
        return {k: money_json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [money_json(x) for x in v]
    return v


FIELDS = ("gross", "ssf_employee", "ssf_employer", "cit", "other_retirement", "tds", "net_pay")
ZERO = Decimal("0.00")


def _payslips(db: Session, company_id: int, fiscal_year: str, employee_id: int | None, include_drafts: bool):
    q = (
        select(Payslip, PayrollRun)
        .join(PayrollRun, Payslip.run_id == PayrollRun.id)
        .where(PayrollRun.company_id == company_id, PayrollRun.fiscal_year == fiscal_year)
        .order_by(PayrollRun.month)
    )
    if employee_id is not None:
        q = q.where(Payslip.employee_id == employee_id)
    if not include_drafts:
        q = q.where(PayrollRun.status == RunStatus.FINALIZED)
    return db.execute(q).all()


def annual_statement(db: Session, company_id: int, employee: Employee, fiscal_year: str, include_drafts: bool) -> dict:
    """One row per month of the fiscal year (empty months included) plus year totals.

    Employees see finalized months only; HR can include the current draft, flagged as such.
    """
    rows = {m: None for m in range(1, 13)}
    latest = None
    for slip, run in _payslips(db, company_id, fiscal_year, employee.id, include_drafts):
        rows[run.month] = {
            "month": run.month,
            "month_label": month_label(fiscal_year, run.month),
            "payment_date": run.payment_date,
            "status": run.status,
            "payslip_id": slip.id,
            "run_id": run.id,
            **{f: getattr(slip, f) for f in FIELDS},
        }
        latest = slip
    months = [r or {"month": m, "month_label": month_label(fiscal_year, m), "status": None} for m, r in rows.items()]
    filled = [r for r in rows.values() if r]
    totals = {f: sum((r[f] for r in filled), ZERO) for f in FIELDS}
    totals["ssf_total"] = totals["ssf_employee"] + totals["ssf_employer"]
    projected = latest.projected_annual_tax if latest else None
    return {
        "employee": {"id": employee.id, "code": employee.code, "name": employee.name, "pan": employee.pan},
        "fiscal_year": fiscal_year,
        "months": months,
        "totals": totals,
        "months_paid": len(filled),
        "projected_annual_tax": projected,
        "tds_remaining": None if projected is None else max(ZERO, projected - totals["tds"]),
    }


def contributions_report(db: Session, company_id: int, fiscal_year: str, include_drafts: bool) -> dict:
    """SSF (11% + 20%) and CIT for every employee and month, with month and year totals."""
    by_emp: dict[int, dict] = {}
    month_totals = {m: {"ssf_employee": ZERO, "ssf_employer": ZERO, "cit": ZERO} for m in range(1, 13)}
    statuses: dict[int, str] = {}
    for slip, run in _payslips(db, company_id, fiscal_year, None, include_drafts):
        statuses[run.month] = run.status
        e = by_emp.setdefault(slip.employee_id, {
            "employee_id": slip.employee_id,
            "code": slip.employee.code,
            "name": slip.employee.name,
            "months": {},
            "totals": {"ssf_employee": ZERO, "ssf_employer": ZERO, "cit": ZERO},
        })
        cell = {"ssf_employee": slip.ssf_employee, "ssf_employer": slip.ssf_employer, "cit": slip.cit}
        e["months"][run.month] = cell
        for k, v in cell.items():
            e["totals"][k] += v
            month_totals[run.month][k] += v
    employees = sorted(by_emp.values(), key=lambda e: e["code"])
    grand = {k: sum((e["totals"][k] for e in employees), ZERO) for k in ("ssf_employee", "ssf_employer", "cit")}
    return {
        "fiscal_year": fiscal_year,
        "months": [
            {"month": m, "month_label": month_label(fiscal_year, m), "status": statuses.get(m), **month_totals[m]}
            for m in range(1, 13)
        ],
        "employees": employees,
        "totals": grand | {"ssf_total": grand["ssf_employee"] + grand["ssf_employer"]},
    }
