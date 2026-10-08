"""HR reports: one employee's year, and the company's SSF/CIT contributions by month."""

import csv
import io

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Membership
from app.security import viewer
from app.services.statements import annual_statement, contributions_report, money_json

from .employees import fy_from_path, get_employee

router = APIRouter(prefix="/companies/{company_id}", tags=["reports"])


@router.get("/employees/{employee_id}/annual/{fy}")
def employee_annual(company_id: int, employee_id: int, fy: str, include_drafts: bool = True,
                    _: Membership = Depends(viewer), db: Session = Depends(get_db)):
    return money_json(annual_statement(db, company_id, get_employee(db, company_id, employee_id), fy_from_path(fy), include_drafts))


@router.get("/reports/contributions/{fy}.csv")
def contributions_csv(company_id: int, fy: str, include_drafts: bool = False,
                      _: Membership = Depends(viewer), db: Session = Depends(get_db)):
    """One row per employee per month: for SSF and CIT remittance and reconciliation."""
    fiscal_year = fy_from_path(fy)
    r = contributions_report(db, company_id, fiscal_year, include_drafts)
    labels = {m["month"]: m["month_label"] for m in r["months"]}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["employee_code", "employee_name", "fiscal_year", "month", "month_label",
                "ssf_employee_11pct", "ssf_employer_20pct", "ssf_total", "cit"])
    for e in r["employees"]:
        for month, c in sorted(e["months"].items()):
            w.writerow([e["code"], e["name"], fiscal_year, month, labels[month], c["ssf_employee"], c["ssf_employer"],
                        c["ssf_employee"] + c["ssf_employer"], c["cit"]])
        t = e["totals"]
        w.writerow([e["code"], e["name"], fiscal_year, "year", "Year total", t["ssf_employee"], t["ssf_employer"],
                    t["ssf_employee"] + t["ssf_employer"], t["cit"]])
    name = f"ssf-cit-{fiscal_year.replace('/', '-')}.csv"
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/reports/tds/{fy}.csv")
def tds_ird_csv(company_id: int, fy: str, include_drafts: bool = False,
                _: Membership = Depends(viewer), db: Session = Depends(get_db)):
    """Salary TDS per employee per period with PAN, laid out like the IRD TDS detail sheet."""
    fiscal_year = fy_from_path(fy)
    r = contributions_report(db, company_id, fiscal_year, include_drafts)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["s.n.", "PAN", "Name", *[m["month_label"] for m in r["months"]], "TOTAL"])
    for n, e in enumerate(r["employees"], start=1):
        w.writerow([n, e["pan"] or "", e["name"], *[e["months"].get(m["month"], {}).get("tds", "0.00") for m in r["months"]],
                    e["totals"]["tds"]])
    w.writerow(["", "", "Total", *[m["tds"] for m in r["months"]], r["totals"]["tds"]])
    name = f"tds-ird-{fiscal_year.replace('/', '-')}.csv"
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


# Declared after the .csv route: "{fy}" would otherwise also match "2083-84.csv".
@router.get("/reports/contributions/{fy}")
def contributions(company_id: int, fy: str, include_drafts: bool = False,
                  _: Membership = Depends(viewer), db: Session = Depends(get_db)):
    return money_json(contributions_report(db, company_id, fy_from_path(fy), include_drafts))
