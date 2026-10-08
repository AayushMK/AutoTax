from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Membership, Role, User

# EMPLOYEE ranks below VIEWER: an employee login never passes any HR check (no one else's pay).
ROLE_RANK = {Role.EMPLOYEE: -1, Role.VIEWER: 0, Role.ACCOUNTANT: 1, Role.ADMIN: 2}
bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())


def issue_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_ttl_minutes)
    return jwt.encode({"sub": str(user.id), "exp": exp}, settings.jwt_secret, algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in")
    try:
        user_id = int(jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user no longer exists")
    return user


def require_role(min_role: Role):
    """Dependency: the caller is a member of path param `company_id` with at least `min_role`."""

    def dep(company_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Membership:
        m = db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.company_id == company_id))
        if m is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "company not found")
        if ROLE_RANK[m.role] < ROLE_RANK[min_role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires {min_role} role")
        return m

    return dep


def self_service(company_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Membership:
    """Any member whose login is linked to an employee record; scopes "My pay" to that record."""
    m = db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.company_id == company_id))
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "company not found")
    if m.employee_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "your login isn't linked to an employee record")
    return m


viewer = require_role(Role.VIEWER)
accountant = require_role(Role.ACCOUNTANT)
admin = require_role(Role.ADMIN)
