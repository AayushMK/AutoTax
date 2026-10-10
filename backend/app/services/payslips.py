"""One payslip as shown to HR and to the employee: pay lines, deductions and employee details."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Payslip, TaxProfile

from .calendar import period
from .payroll import tds_start_period


def payslip_detail(db: Session, p: Payslip) -> dict:
    run = p.run
    cal = db.get(Company, run.company_id).pay_calendar
    e = p.employee
    tp = db.scalar(select(TaxProfile).where(TaxProfile.employee_id == e.id, TaxProfile.fiscal_year == run.fiscal_year))
    start = tds_start_period(db, run.company_id, run.fiscal_year)
    return {
        "id": p.id, "employee_id": p.employee_id, "employee_code": e.code, "employee_name": e.name,
        "gross": p.gross, "ssf_employee": p.ssf_employee, "ssf_employer": p.ssf_employer, "cit": p.cit, "tds": p.tds,
        "net_pay": p.net_pay, "projected_annual_tax": p.projected_annual_tax,
        "share": f"{p.share_num}/{p.share_den}" if p.share_den != 1 else None,
        "projected_tax_without_cit": p.projected_tax_without_cit,
        "month": p.month, "month_label": period(run.fiscal_year, p.month, cal).label, "fiscal_year": run.fiscal_year,
        "payment_date": run.payment_date, "run_status": run.status,
        "basic": p.basic, "other_retirement": p.other_retirement, "projected_taxable_income": p.projected_taxable_income,
        "employee": {
            "code": e.code, "name": e.name, "pan": e.pan, "department": e.department, "designation": e.designation,
            "cit_number": e.cit_number, "ssf_number": e.ssf_number, "bank_account": e.bank_account, "joined_on": e.joined_on,
            "marital_status": "Married (couple)" if tp and tp.filing == "couple" else "Unmarried / single",
        },
        "tds_starts": period(run.fiscal_year, start, cal).label if start > 1 else None,
        "inputs": p.inputs, "trace": p.trace,
    }
