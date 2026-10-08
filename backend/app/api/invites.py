"""Invite links: HR creates one, the person opens it and sets their own password."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Invite, Membership, Role, User
from app.security import admin, hash_password, issue_token, verify_password
from app.services import audit

from .employees import get_employee
from .schemas import AcceptInviteIn, InviteIn, InviteInfo, InviteOut, TokenOut

router = APIRouter(tags=["invites"])
INVITE_DAYS = 7


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _out(i: Invite, token: str | None = None) -> InviteOut:
    return InviteOut(id=i.id, email=i.email, role=i.role, employee_id=i.employee_id,
                     employee_name=i.employee.name if i.employee else None, expires_at=i.expires_at, token=token)


def _open_invite(db: Session, token: str) -> Invite:
    i = db.scalar(select(Invite).where(Invite.token_hash == _hash(token)))
    if i is None or i.accepted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "this invite link is invalid or has already been used")
    if i.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_410_GONE, "this invite link has expired; ask HR for a new one")
    return i


@router.post("/companies/{company_id}/invites", response_model=InviteOut, status_code=201)
def create_invite(company_id: int, body: InviteIn, m: Membership = Depends(admin), db: Session = Depends(get_db)):
    if body.role == Role.EMPLOYEE and body.employee_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "an employee login must be linked to an employee record")
    if body.employee_id is not None:
        get_employee(db, company_id, body.employee_id)
        linked = db.scalar(select(Membership).where(Membership.employee_id == body.employee_id))
        if linked:
            raise HTTPException(status.HTTP_409_CONFLICT, "this employee already has a login")
    email = body.email.lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user and db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.company_id == company_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "this person already has access to the company")
    token = secrets.token_urlsafe(32)
    i = Invite(company_id=company_id, email=email, role=body.role, employee_id=body.employee_id,
               token_hash=_hash(token), created_by=m.user_id,
               expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_DAYS))
    db.add(i)
    db.flush()
    audit.record(db, company_id=company_id, user_id=m.user_id, action="invite.create", entity="invite", entity_id=i.id,
                 data={"email": email, "role": body.role, "employee_id": body.employee_id})
    db.commit()
    return _out(i, token)


@router.get("/companies/{company_id}/invites", response_model=list[InviteOut])
def list_invites(company_id: int, _: Membership = Depends(admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(Invite).where(
        Invite.company_id == company_id, Invite.accepted_at.is_(None), Invite.expires_at > datetime.now(timezone.utc)
    ).order_by(Invite.created_at.desc())).all()
    return [_out(i) for i in rows]


@router.delete("/companies/{company_id}/invites/{invite_id}", status_code=204)
def cancel_invite(company_id: int, invite_id: int, m: Membership = Depends(admin), db: Session = Depends(get_db)):
    i = db.get(Invite, invite_id)
    if i is None or i.company_id != company_id or i.accepted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invite not found")
    db.delete(i)
    audit.record(db, company_id=company_id, user_id=m.user_id, action="invite.cancel", entity="invite", entity_id=invite_id,
                 data={"email": i.email})
    db.commit()
    return Response(status_code=204)


@router.get("/auth/invites/{token}", response_model=InviteInfo)
def invite_info(token: str, db: Session = Depends(get_db)):
    i = _open_invite(db, token)
    has_account = db.scalar(select(User).where(func.lower(User.email) == i.email)) is not None
    return InviteInfo(company_id=i.company_id, company_name=i.company.name, email=i.email, role=i.role,
                      employee_name=i.employee.name if i.employee else None, has_account=has_account)


@router.post("/auth/invites/{token}/accept", response_model=TokenOut)
def accept_invite(token: str, body: AcceptInviteIn, db: Session = Depends(get_db)):
    i = _open_invite(db, token)
    user = db.scalar(select(User).where(func.lower(User.email) == i.email))
    if user is None:
        if not body.name.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "enter your name")
        user = User(email=i.email, name=body.name.strip(), password_hash=hash_password(body.password))
        db.add(user)
        db.flush()
    elif not verify_password(body.password, user.password_hash):
        # Existing account (e.g. HR person at a second company): prove it's theirs.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong password for your existing account")
    if db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.company_id == i.company_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "you already have access to this company")
    db.add(Membership(user_id=user.id, company_id=i.company_id, role=i.role, employee_id=i.employee_id))
    i.accepted_at = datetime.now(timezone.utc)
    i.accepted_by = user.id
    audit.record(db, company_id=i.company_id, user_id=user.id, action="invite.accept", entity="invite", entity_id=i.id,
                 data={"email": i.email, "role": i.role})
    db.commit()
    return TokenOut(token=issue_token(user))
