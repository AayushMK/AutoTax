"""Employee self-service: only the caller's own employee record, only finalized months."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company, Employee, Membership, Payslip, PayrollRun, RunStatus
from app.security import self_service
from app.services.calendar import fiscal_year_of, month_label
from app.services.statements import annual_statement, money_json

from .employees import fy_from_path
from .schemas import EmployeeOut, PayslipDetail

router = APIRouter(prefix="/companies/{company_id}/me", tags=["my pay"])


@router.get("", response_model=EmployeeOut)
def my_record(company_id: int, m: Membership = Depends(self_service), db: Session = Depends(get_db)):
    return db.get(Employee, m.employee_id)


@router.get("/years")
def my_years(company_id: int, m: Membership = Depends(self_service), db: Session = Depends(get_db)):
    """Fiscal years with at least one finalized payslip, newest first."""
    years = db.scalars(
        select(PayrollRun.fiscal_year).join(Payslip, Payslip.run_id == PayrollRun.id)
        .where(Payslip.employee_id == m.employee_id, PayrollRun.status == RunStatus.FINALIZED)
        .distinct()
    ).all()
    return sorted(set(years) | {fiscal_year_of(date.today())}, reverse=True)


@router.get("/annual/{fy}")
def my_annual(company_id: int, fy: str, m: Membership = Depends(self_service), db: Session = Depends(get_db)):
    return money_json(annual_statement(db, company_id, db.get(Employee, m.employee_id), fy_from_path(fy), include_drafts=False))


@router.get("/payslips/{payslip_id}", response_model=PayslipDetail)
def my_payslip(company_id: int, payslip_id: int, m: Membership = Depends(self_service), db: Session = Depends(get_db)):
    p = db.get(Payslip, payslip_id)
    # Same answer for "someone else's" and "doesn't exist": never confirm other payslips exist.
    if p is None or p.employee_id != m.employee_id or p.run.company_id != company_id or p.run.status != RunStatus.FINALIZED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "payslip not found")
    return PayslipDetail(
        id=p.id, employee_id=p.employee_id, employee_code=p.employee.code, employee_name=p.employee.name,
        gross=p.gross, ssf_employee=p.ssf_employee, ssf_employer=p.ssf_employer, cit=p.cit, tds=p.tds,
        net_pay=p.net_pay, projected_annual_tax=p.projected_annual_tax, month=p.month, basic=p.basic,
        other_retirement=p.other_retirement, projected_taxable_income=p.projected_taxable_income,
        share=f"{p.share_num}/{p.share_den}" if p.share_den != 1 else None,
        projected_tax_without_cit=p.projected_tax_without_cit,
        inputs=p.inputs | {"month_label": month_label(p.run.fiscal_year, p.month, db.get(Company, company_id).pay_calendar)},
        trace=p.trace,
    )
