from sqlalchemy.orm import Session

from app.models import AuditLog


def record(db: Session, *, company_id: int | None, user_id: int | None, action: str, entity: str,
           entity_id: int | None = None, data: dict | None = None) -> None:
    db.add(AuditLog(company_id=company_id, user_id=user_id, action=action, entity=entity,
                    entity_id=entity_id, data=_jsonable(data or {})))


def _jsonable(v):
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, (str, int, bool)) or v is None:
        return v
    return str(v)  # Decimal, date, enums
