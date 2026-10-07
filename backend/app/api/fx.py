from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import FxRateRow, Membership
from app.security import accountant, viewer
from app.services import audit, fx_store

from .schemas import FxOverrideIn, FxRateOut, FxSyncIn

router = APIRouter(prefix="/companies/{company_id}/fx", tags=["fx"])


@router.get("/rates", response_model=list[FxRateOut])
def rates(company_id: int, currency: str, start: date, end: date, _: Membership = Depends(viewer),
          db: Session = Depends(get_db)):
    return db.scalars(select(FxRateRow).where(
        FxRateRow.currency == currency.upper(), FxRateRow.on.between(start, end),
        or_(FxRateRow.company_id.is_(None), FxRateRow.company_id == company_id),
    ).order_by(FxRateRow.on, FxRateRow.source)).all()


@router.post("/sync")
def sync(company_id: int, body: FxSyncIn, m: Membership = Depends(accountant), db: Session = Depends(get_db)):
    if (body.end - body.start).days > 366 or body.end < body.start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "range must be 0–366 days")
    try:
        n = fx_store.sync_nrb(db, body.start, body.end, {c.upper() for c in body.currencies} if body.currencies else None)
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"NRB rates unavailable: {e}")
    audit.record(db, company_id=company_id, user_id=m.user_id, action="fx.sync", entity="fx_rate",
                 data={"start": body.start, "end": body.end, "rates": n})
    db.commit()
    return {"rates": n}


@router.post("/overrides", response_model=FxRateOut, status_code=201)
def override(company_id: int, body: FxOverrideIn, m: Membership = Depends(accountant), db: Session = Depends(get_db)):
    row = fx_store.set_override(db, company_id=company_id, currency=body.currency, on=body.on, buy=body.buy,
                                sell=body.sell, unit=body.unit, reason=body.reason, user_id=m.user_id)
    db.flush()
    audit.record(db, company_id=company_id, user_id=m.user_id, action="fx.override", entity="fx_rate", entity_id=row.id,
                 data=body.model_dump(mode="json"))
    db.commit()
    return row
