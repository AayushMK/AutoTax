from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditLog, Company, Membership, PayrollRun, Role, TdsPolicy, User
from app.services.calendar import period, periods
from app.security import admin, current_user, viewer
from app.services import audit

from .schemas import AuditOut, CompanyIn, CompanyOut, MemberIn, MemberOut, TdsPolicyIn, TdsPolicyOut

router = APIRouter(tags=["companies"])


@router.post("/companies", response_model=CompanyOut, status_code=201)
def create_company(body: CompanyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = Company(name=body.name, pan=body.pan, pay_calendar=body.pay_calendar)
    db.add(c)
    db.flush()
    db.add(Membership(user_id=user.id, company_id=c.id, role=Role.ADMIN))
    audit.record(db, company_id=c.id, user_id=user.id, action="company.create", entity="company", entity_id=c.id)
    db.commit()
    return c


@router.get("/companies/{company_id}", response_model=CompanyOut)
def get_company(company_id: int, m: Membership = Depends(viewer)):
    return m.company


@router.put("/companies/{company_id}", response_model=CompanyOut)
def update_company(company_id: int, body: CompanyIn, m: Membership = Depends(admin), db: Session = Depends(get_db)):
    c = m.company
    if body.pay_calendar != c.pay_calendar and db.scalar(
        select(func.count()).select_from(PayrollRun).where(PayrollRun.company_id == company_id)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "the payroll calendar can't change once payroll exists: past periods would change meaning")
    before = {"name": c.name, "pan": c.pan, "pay_calendar": c.pay_calendar}
    c.name, c.pan, c.pay_calendar = body.name, body.pan, body.pay_calendar
    audit.record(db, company_id=company_id, user_id=m.user_id, action="company.update", entity="company",
                 entity_id=company_id, data={"before": before, "after": body.model_dump()})
    db.commit()
    return c


@router.get("/companies/{company_id}/members", response_model=list[MemberOut])
def members(company_id: int, _: Membership = Depends(viewer), db: Session = Depends(get_db)):
    rows = db.scalars(select(Membership).where(Membership.company_id == company_id)).all()
    return [
        MemberOut(user_id=r.user_id, email=r.user.email, name=r.user.name, role=r.role, employee_id=r.employee_id,
                  employee_name=r.employee.name if r.employee else None)
        for r in sorted(rows, key=lambda r: (r.role == Role.EMPLOYEE, r.user.name))
    ]


@router.post("/companies/{company_id}/members", response_model=MemberOut, status_code=201)
def add_member(company_id: int, body: MemberIn, m: Membership = Depends(admin), db: Session = Depends(get_db)):
    """Change the role of someone who already has an account (new people get an invite link)."""
    if body.role == Role.EMPLOYEE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "employee logins are created with an invite linked to their record")
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no account with that email; ask them to sign up first")
    existing = db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.company_id == company_id))
    if existing:
        existing.role = body.role
    else:
        db.add(Membership(user_id=user.id, company_id=company_id, role=body.role))
    audit.record(db, company_id=company_id, user_id=m.user_id, action="member.set", entity="user", entity_id=user.id,
                 data={"role": body.role})
    db.commit()
    return MemberOut(user_id=user.id, email=user.email, name=user.name, role=body.role)


@router.delete("/companies/{company_id}/members/{user_id}", status_code=204)
def remove_member(company_id: int, user_id: int, m: Membership = Depends(admin), db: Session = Depends(get_db)):
    """Revoke someone's access (e.g. an employee who left). Their payslips are kept."""
    if user_id == m.user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "you can't remove your own access")
    target = db.scalar(select(Membership).where(Membership.user_id == user_id, Membership.company_id == company_id))
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "member not found")
    if target.role == Role.ADMIN and db.scalar(
        select(func.count()).select_from(Membership).where(Membership.company_id == company_id, Membership.role == Role.ADMIN)
    ) == 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "a company needs at least one HR admin")
    audit.record(db, company_id=company_id, user_id=m.user_id, action="member.remove", entity="user", entity_id=user_id,
                 data={"role": target.role})
    db.delete(target)
    db.commit()
    return Response(status_code=204)


def _policy_out(c: Company, fiscal_year: str, start: int) -> TdsPolicyOut:
    return TdsPolicyOut(fiscal_year=fiscal_year, start_period=start, start_label=period(fiscal_year, start, c.pay_calendar).label)


@router.get("/companies/{company_id}/tds-policy/{fy}", response_model=TdsPolicyOut)
def get_tds_policy(company_id: int, fy: str, m: Membership = Depends(viewer), db: Session = Depends(get_db)):
    fiscal_year = fy.replace("-", "/")
    p = db.scalar(select(TdsPolicy).where(TdsPolicy.company_id == company_id, TdsPolicy.fiscal_year == fiscal_year))
    return _policy_out(m.company, fiscal_year, p.start_period if p else 1)


@router.put("/companies/{company_id}/tds-policy/{fy}", response_model=TdsPolicyOut)
def set_tds_policy(company_id: int, fy: str, body: TdsPolicyIn, m: Membership = Depends(admin), db: Session = Depends(get_db)):
    """Start withholding TDS in a later month; earlier months withhold nothing and the rest catch up."""
    fiscal_year = fy.replace("-", "/")
    if body.start_period > len(periods(fiscal_year, m.company.pay_calendar)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "that month isn't in this fiscal year")
    p = db.scalar(select(TdsPolicy).where(TdsPolicy.company_id == company_id, TdsPolicy.fiscal_year == fiscal_year))
    if p is None:
        p = TdsPolicy(company_id=company_id, fiscal_year=fiscal_year)
        db.add(p)
    before = p.start_period
    p.start_period = body.start_period
    audit.record(db, company_id=company_id, user_id=m.user_id, action="tds_policy.set", entity="company", entity_id=company_id,
                 data={"fiscal_year": fiscal_year, "before": before, "start_period": body.start_period})
    db.commit()
    return _policy_out(m.company, fiscal_year, body.start_period)


@router.get("/companies/{company_id}/audit", response_model=list[AuditOut])
def audit_log(company_id: int, limit: int = 200, _: Membership = Depends(viewer), db: Session = Depends(get_db)):
    return db.scalars(
        select(AuditLog).where(AuditLog.company_id == company_id).order_by(AuditLog.at.desc()).limit(min(limit, 1000))
    ).all()
