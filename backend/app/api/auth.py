from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company, Membership, Role, User
from app.security import current_user, hash_password, issue_token, verify_password
from app.services import audit

from .schemas import LoginIn, MembershipOut, MeOut, SignupIn, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenOut, status_code=201)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(func.lower(User.email) == body.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "an account with this email already exists")
    user = User(email=body.email.lower(), name=body.name, password_hash=hash_password(body.password))
    company = Company(name=body.company_name, pan=body.company_pan)
    db.add_all([user, company])
    db.flush()
    db.add(Membership(user_id=user.id, company_id=company.id, role=Role.ADMIN))
    audit.record(db, company_id=company.id, user_id=user.id, action="company.create", entity="company", entity_id=company.id)
    db.commit()
    return TokenOut(token=issue_token(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong email or password")
    return TokenOut(token=issue_token(user))


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ms = db.scalars(select(Membership).where(Membership.user_id == user.id)).all()
    return MeOut(
        id=user.id, email=user.email, name=user.name,
        memberships=[MembershipOut(company_id=m.company_id, company_name=m.company.name, role=m.role) for m in ms],
    )
