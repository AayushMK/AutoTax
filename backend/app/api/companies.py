from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditLog, Company, Membership, Role, User
from app.security import admin, current_user, viewer
from app.services import audit

from .schemas import AuditOut, CompanyIn, CompanyOut, MemberIn, MemberOut

router = APIRouter(tags=["companies"])


@router.post("/companies", response_model=CompanyOut, status_code=201)
def create_company(body: CompanyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = Company(name=body.name, pan=body.pan)
    db.add(c)
    db.flush()
    db.add(Membership(user_id=user.id, company_id=c.id, role=Role.ADMIN))
    audit.record(db, company_id=c.id, user_id=user.id, action="company.create", entity="company", entity_id=c.id)
    db.commit()
    return c


@router.get("/companies/{company_id}", response_model=CompanyOut)
def get_company(company_id: int, m: Membership = Depends(viewer)):
    return m.company


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


@router.get("/companies/{company_id}/audit", response_model=list[AuditOut])
def audit_log(company_id: int, limit: int = 200, _: Membership = Depends(viewer), db: Session = Depends(get_db)):
    return db.scalars(
        select(AuditLog).where(AuditLog.company_id == company_id).order_by(AuditLog.at.desc()).limit(min(limit, 1000))
    ).all()
