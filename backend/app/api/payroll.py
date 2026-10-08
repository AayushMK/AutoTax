import csv
import io
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company, Membership, Payslip, PayrollRun, RunAdjustment, RunStatus
from app.security import accountant, viewer
from app.services import audit, payroll
from app.services.calendar import period, periods

from .employees import get_employee
from .schemas import (
    AdjustmentIn,
    AdjustmentOut,
    FinalizeIn,
    ImportIn,
    PayslipDetail,
    PeriodOut,
    PayslipSummary,
    RunDetail,
    RunIn,
    RunOut,
    Totals,
)

router = APIRouter(prefix="/companies/{company_id}/payroll-runs", tags=["payroll"])


def get_run(db: Session, company_id: int, run_id: int) -> PayrollRun:
    r = db.get(PayrollRun, run_id)
    if r is None or r.company_id != company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "payroll run not found")
    return r


def _payroll_error(e: payroll.PayrollError) -> HTTPException:
    detail = {"message": str(e), "problems": e.problems}
    if isinstance(e, payroll.RulesNotAcknowledged):
        detail["rule_set"] = e.rule_set
        detail["code"] = "rules_unverified"
        return HTTPException(status.HTTP_409_CONFLICT, detail)
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


def run_out(r: PayrollRun, cal: str) -> dict:
    p = period(r.fiscal_year, r.month, cal)
    return {
        "id": r.id, "fiscal_year": r.fiscal_year, "month": r.month, "month_label": p.label,
        "period_start": p.start, "period_end": p.end, "source": r.source,
        "payment_date": r.payment_date, "status": r.status, "rule_set": r.rule_set, "rule_review_status": r.rule_review_status,
        "warnings": r.warnings or [], "acknowledged_unverified": r.acknowledged_unverified or [],
        "computed_at": r.computed_at, "finalized_at": r.finalized_at,
    }


def summary(p: Payslip) -> dict:
    return {
        "id": p.id, "employee_id": p.employee_id, "employee_code": p.employee.code, "employee_name": p.employee.name,
        "gross": p.gross, "ssf_employee": p.ssf_employee, "ssf_employer": p.ssf_employer, "cit": p.cit, "tds": p.tds,
        "net_pay": p.net_pay, "projected_annual_tax": p.projected_annual_tax,
        "share": f"{p.share_num}/{p.share_den}" if p.share_den != 1 else None,
        "projected_tax_without_cit": p.projected_tax_without_cit,
    }


def run_detail(r: PayrollRun, cal: str) -> RunDetail:
    slips = sorted(r.payslips, key=lambda p: p.employee.code)
    tot = lambda f: sum((getattr(p, f) for p in slips), Decimal("0.00"))  # noqa: E731
    return RunDetail(
        **run_out(r, cal),
        payslips=[PayslipSummary(**summary(p)) for p in slips],
        adjustments=[AdjustmentOut.model_validate(a) for a in r.adjustments],
        totals=Totals(gross=tot("gross"), ssf_employee=tot("ssf_employee"), ssf_employer=tot("ssf_employer"),
                      cit=tot("cit"), tds=tot("tds"), net_pay=tot("net_pay")),
    )


def cal_of(db: Session, company_id: int) -> str:
    return db.get(Company, company_id).pay_calendar


@router.get("", response_model=list[RunOut])
def list_runs(company_id: int, _: Membership = Depends(viewer), db: Session = Depends(get_db)):
    cal = cal_of(db, company_id)
    runs = db.scalars(select(PayrollRun).where(PayrollRun.company_id == company_id)
                      .order_by(PayrollRun.fiscal_year.desc(), PayrollRun.month.desc())).all()
    return [run_out(r, cal) for r in runs]


@router.get("/periods/{fy}", response_model=list[PeriodOut])
def list_periods(company_id: int, fy: str, _: Membership = Depends(viewer), db: Session = Depends(get_db)):
    """The fiscal year's pay periods in the company's calendar, with any run already started."""
    fiscal_year = fy.replace("-", "/")
    runs = {r.month: r for r in db.scalars(select(PayrollRun).where(
        PayrollRun.company_id == company_id, PayrollRun.fiscal_year == fiscal_year))}
    try:
        ps = periods(fiscal_year, cal_of(db, company_id))
    except Exception:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "fiscal year must look like 2083-84")
    return [PeriodOut(index=p.index, label=p.label, start=p.start, end=p.end,
                      run_id=runs[p.index].id if p.index in runs else None,
                      status=runs[p.index].status if p.index in runs else None,
                      source=runs[p.index].source if p.index in runs else None) for p in ps]


@router.post("", response_model=RunDetail, status_code=201)
def create_run(company_id: int, body: RunIn, m: Membership = Depends(accountant), db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    try:
        r = payroll.create_run(db, company, body.payment_date, m.user_id,
                               fiscal_year=body.fiscal_year.replace("-", "/") if body.fiscal_year else None,
                               period_index=body.period)
    except payroll.PayrollError as e:
        raise _payroll_error(e)
    db.commit()
    return run_detail(r, company.pay_calendar)


@router.get("/{run_id}", response_model=RunDetail)
def get_run_detail(company_id: int, run_id: int, _: Membership = Depends(viewer), db: Session = Depends(get_db)):
    return run_detail(get_run(db, company_id, run_id), cal_of(db, company_id))


@router.put("/{run_id}/import", response_model=RunDetail)
def import_figures(company_id: int, run_id: int, body: ImportIn, m: Membership = Depends(accountant),
                   db: Session = Depends(get_db)):
    """Enter a month that was paid before the company used AutoTax."""
    r = get_run(db, company_id, run_id)
    try:
        payroll.import_run(db, r, [row.model_dump() for row in body.rows], body.gross_includes_employer_ssf, m.user_id)
    except payroll.PayrollError as e:
        raise _payroll_error(e)
    db.commit()
    return run_detail(r, cal_of(db, company_id))


@router.delete("/{run_id}", status_code=204)
def delete_run(company_id: int, run_id: int, m: Membership = Depends(accountant), db: Session = Depends(get_db)):
    r = get_run(db, company_id, run_id)
    if r.status != RunStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "finalized runs cannot be deleted")
    audit.record(db, company_id=company_id, user_id=m.user_id, action="payroll.delete", entity="payroll_run",
                 entity_id=r.id, data={"fiscal_year": r.fiscal_year, "month": r.month})
    db.delete(r)
    db.commit()
    return Response(status_code=204)


@router.post("/{run_id}/adjustments", response_model=AdjustmentOut, status_code=201)
def add_adjustment(company_id: int, run_id: int, body: AdjustmentIn, m: Membership = Depends(accountant),
                   db: Session = Depends(get_db)):
    r = get_run(db, company_id, run_id)
    if r.status != RunStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "run is finalized")
    get_employee(db, company_id, body.employee_id)
    a = RunAdjustment(run_id=r.id, **body.model_dump() | {"currency": body.currency.upper()})
    db.add(a)
    r.computed_at = None  # inputs changed: payslips are stale until recomputed
    db.flush()
    audit.record(db, company_id=company_id, user_id=m.user_id, action="payroll.adjustment.add", entity="payroll_run",
                 entity_id=r.id, data=body.model_dump(mode="json"))
    db.commit()
    return a


@router.delete("/{run_id}/adjustments/{adjustment_id}", status_code=204)
def delete_adjustment(company_id: int, run_id: int, adjustment_id: int, m: Membership = Depends(accountant),
                      db: Session = Depends(get_db)):
    r = get_run(db, company_id, run_id)
    a = db.get(RunAdjustment, adjustment_id)
    if a is None or a.run_id != r.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "adjustment not found")
    if r.status != RunStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "run is finalized")
    db.delete(a)
    r.computed_at = None
    audit.record(db, company_id=company_id, user_id=m.user_id, action="payroll.adjustment.delete", entity="payroll_run",
                 entity_id=r.id, data={"adjustment_id": adjustment_id})
    db.commit()
    return Response(status_code=204)


@router.post("/{run_id}/compute", response_model=RunDetail)
def compute(company_id: int, run_id: int, m: Membership = Depends(accountant), db: Session = Depends(get_db)):
    r = get_run(db, company_id, run_id)
    try:
        payroll.compute_run(db, r, m.user_id)
    except payroll.PayrollError as e:
        raise _payroll_error(e)
    db.commit()
    return run_detail(r, cal_of(db, company_id))


@router.post("/{run_id}/finalize", response_model=RunDetail)
def finalize(company_id: int, run_id: int, body: FinalizeIn, m: Membership = Depends(accountant),
             db: Session = Depends(get_db)):
    r = get_run(db, company_id, run_id)
    try:
        payroll.finalize_run(db, r, m.user_id, body.acknowledge_unverified)
    except payroll.PayrollError as e:
        raise _payroll_error(e)
    db.commit()
    return run_detail(r, cal_of(db, company_id))


@router.get("/{run_id}/payslips/{payslip_id}", response_model=PayslipDetail)
def payslip(company_id: int, run_id: int, payslip_id: int, _: Membership = Depends(viewer), db: Session = Depends(get_db)):
    r = get_run(db, company_id, run_id)
    p = db.get(Payslip, payslip_id)
    if p is None or p.run_id != r.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "payslip not found")
    return PayslipDetail(
        **summary(p), month=p.month, basic=p.basic, other_retirement=p.other_retirement,
        projected_taxable_income=p.projected_taxable_income, inputs=p.inputs, trace=p.trace,
    )


@router.get("/{run_id}/tds.csv")
def tds_csv(company_id: int, run_id: int, _: Membership = Depends(viewer), db: Session = Depends(get_db)):
    """Salary TDS sheet for the run (one row per employee) for upload preparation / remittance."""
    r = get_run(db, company_id, run_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["employee_code", "employee_name", "pan", "fiscal_year", "month", "payment_date", "gross_npr",
                "ssf_employee", "ssf_employer", "cit", "taxable_income_projected", "tds", "rule_set", "run_status"])
    for p in sorted(r.payslips, key=lambda p: p.employee.code):
        w.writerow([p.employee.code, p.employee.name, p.employee.pan or "", r.fiscal_year, r.month, r.payment_date,
                    p.gross, p.ssf_employee, p.ssf_employer, p.cit, p.projected_taxable_income, p.tds, r.rule_set, r.status])
    name = f"tds-{r.fiscal_year.replace('/', '-')}-m{r.month:02d}.csv"
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})
