from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Employee, Membership, SalaryStructure, TaxProfile
from app.security import accountant, viewer
from app.services import audit

from .schemas import EmployeeDetail, EmployeeIn, EmployeeOut, SalaryStructureIn, SalaryStructureOut, TaxProfileIn, TaxProfileOut

router = APIRouter(prefix="/companies/{company_id}/employees", tags=["employees"])


def get_employee(db: Session, company_id: int, employee_id: int) -> Employee:
    e = db.get(Employee, employee_id)
    if e is None or e.company_id != company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "employee not found")
    return e


def fy_from_path(fy: str) -> str:
    """URL form '2083-84' → '2083/84'."""
    parts = fy.replace("/", "-").split("-")
    if len(parts) != 2 or not (parts[0].isdigit() and parts[1].isdigit() and len(parts[0]) == 4 and len(parts[1]) == 2):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "fiscal year must look like 2083-84")
    return f"{parts[0]}/{parts[1]}"


@router.get("", response_model=list[EmployeeOut])
def list_employees(company_id: int, _: Membership = Depends(viewer), db: Session = Depends(get_db)):
    return db.scalars(select(Employee).where(Employee.company_id == company_id).order_by(Employee.code)).all()


@router.post("", response_model=EmployeeOut, status_code=201)
def create_employee(company_id: int, body: EmployeeIn, m: Membership = Depends(accountant), db: Session = Depends(get_db)):
    if body.left_on and body.left_on < body.joined_on:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "left_on is before joined_on")
    e = Employee(company_id=company_id, **body.model_dump())
    db.add(e)
    try:
        db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, f"employee code {body.code!r} already exists")
    audit.record(db, company_id=company_id, user_id=m.user_id, action="employee.create", entity="employee",
                 entity_id=e.id, data=body.model_dump())
    db.commit()
    return e


@router.get("/{employee_id}", response_model=EmployeeDetail)
def employee_detail(company_id: int, employee_id: int, _: Membership = Depends(viewer), db: Session = Depends(get_db)):
    return get_employee(db, company_id, employee_id)


@router.put("/{employee_id}", response_model=EmployeeOut)
def update_employee(company_id: int, employee_id: int, body: EmployeeIn, m: Membership = Depends(accountant),
                    db: Session = Depends(get_db)):
    e = get_employee(db, company_id, employee_id)
    before = EmployeeIn.model_validate(e, from_attributes=True).model_dump()
    for k, v in body.model_dump().items():
        setattr(e, k, v)
    try:
        db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, f"employee code {body.code!r} already exists")
    audit.record(db, company_id=company_id, user_id=m.user_id, action="employee.update", entity="employee",
                 entity_id=e.id, data={"before": before, "after": body.model_dump()})
    db.commit()
    return e


@router.put("/{employee_id}/tax-profiles/{fy}", response_model=TaxProfileOut)
def set_tax_profile(company_id: int, employee_id: int, fy: str, body: TaxProfileIn, m: Membership = Depends(accountant),
                    db: Session = Depends(get_db)):
    e = get_employee(db, company_id, employee_id)
    fiscal_year = fy_from_path(fy)
    tp = db.scalar(select(TaxProfile).where(TaxProfile.employee_id == e.id, TaxProfile.fiscal_year == fiscal_year))
    if tp is None:
        tp = TaxProfile(employee_id=e.id, fiscal_year=fiscal_year)
        db.add(tp)
    for k, v in body.model_dump().items():
        setattr(tp, k, v)
    audit.record(db, company_id=company_id, user_id=m.user_id, action="tax_profile.set", entity="employee",
                 entity_id=e.id, data={"fiscal_year": fiscal_year, **body.model_dump()})
    db.commit()
    return tp


@router.post("/{employee_id}/salary-structures", response_model=SalaryStructureOut, status_code=201)
def add_structure(company_id: int, employee_id: int, body: SalaryStructureIn, m: Membership = Depends(accountant),
                  db: Session = Depends(get_db)):
    e = get_employee(db, company_id, employee_id)
    if not any(c.kind == "basic" for c in body.components):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "a salary structure needs a basic salary component")
    s = SalaryStructure(
        employee_id=e.id, effective_from=body.effective_from,
        components=[c.model_dump(mode="json") for c in body.components],
        cit_monthly=body.cit_monthly, other_retirement_monthly=body.other_retirement_monthly,
    )
    db.add(s)
    try:
        db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "a structure already starts on that date")
    audit.record(db, company_id=company_id, user_id=m.user_id, action="salary_structure.add", entity="employee",
                 entity_id=e.id, data=body.model_dump(mode="json"))
    db.commit()
    return s


@router.delete("/{employee_id}/salary-structures/{structure_id}", status_code=204)
def delete_structure(company_id: int, employee_id: int, structure_id: int, m: Membership = Depends(accountant),
                     db: Session = Depends(get_db)):
    e = get_employee(db, company_id, employee_id)
    s = db.get(SalaryStructure, structure_id)
    if s is None or s.employee_id != e.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "salary structure not found")
    db.delete(s)  # finalized payslips keep their own copy of the inputs
    audit.record(db, company_id=company_id, user_id=m.user_id, action="salary_structure.delete", entity="employee",
                 entity_id=e.id, data={"structure_id": structure_id, "effective_from": s.effective_from})
    db.commit()
    return Response(status_code=204)
