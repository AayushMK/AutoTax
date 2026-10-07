"""Exchange rates in the database: NRB rates (shared) + per-company overrides."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.engine.fx import MAX_FALLBACK_DAYS, FxRate, FxTable
from app.fx import nrb
from app.models import FxRateRow

NRB = "NRB"
OVERRIDE = "OVERRIDE"


def sync_nrb(db: Session, start: date, end: date, currencies: set[str] | None = None, fetch=nrb.fetch_rates) -> int:
    rates = fetch(start, end, currencies)
    now = datetime.now(timezone.utc)
    for r in rates:
        stmt = insert(FxRateRow).values(
            currency=r.currency, on=r.on, buy=r.buy, sell=r.sell, unit=r.unit, source=NRB, company_id=None, fetched_at=now,
        )
        db.execute(stmt.on_conflict_do_update(
            index_elements=["currency", "on", "source", "company_id"],
            set_={"buy": stmt.excluded.buy, "sell": stmt.excluded.sell, "unit": stmt.excluded.unit, "fetched_at": now},
        ))
    return len(rates)


def set_override(db: Session, *, company_id: int, currency: str, on: date, buy: Decimal, sell: Decimal,
                 unit: int, reason: str, user_id: int) -> FxRateRow:
    if not reason.strip():
        raise ValueError("an override needs a reason (e.g. bank credit advice number)")
    row = db.scalar(select(FxRateRow).where(
        FxRateRow.company_id == company_id, FxRateRow.currency == currency.upper(), FxRateRow.on == on, FxRateRow.source == OVERRIDE
    ))
    if row is None:
        row = FxRateRow(company_id=company_id, currency=currency.upper(), on=on, source=OVERRIDE)
        db.add(row)
    row.buy, row.sell, row.unit, row.override_reason, row.created_by = buy, sell, unit, reason, user_id
    row.fetched_at = datetime.now(timezone.utc)
    return row


def table_for(db: Session, company_id: int, currencies: set[str], on: date) -> FxTable:
    """Rates usable for a payment on `on`: NRB + this company's overrides, within the fallback window."""
    currencies = {c.upper() for c in currencies} - {"NPR"}
    if not currencies:
        return FxTable()
    window_start = on - timedelta(days=MAX_FALLBACK_DAYS)
    if settings.fetch_fx_automatically:
        _ensure(db, currencies, window_start, on)
    rows = db.scalars(select(FxRateRow).where(
        FxRateRow.currency.in_(currencies), FxRateRow.on.between(window_start, on),
        or_(FxRateRow.company_id.is_(None), FxRateRow.company_id == company_id),
    )).all()
    return FxTable([to_engine(r) for r in rows])


def _ensure(db: Session, currencies: set[str], start: date, end: date) -> None:
    have = set(db.execute(select(FxRateRow.currency).where(
        FxRateRow.currency.in_(currencies), FxRateRow.on.between(start, end), FxRateRow.source == NRB
    )).scalars())
    if currencies - have:
        try:
            sync_nrb(db, start, end, currencies)
        except Exception:  # offline / NRB down: fall through; conversion reports the missing rate
            pass


def to_engine(r: FxRateRow) -> FxRate:
    return FxRate(currency=r.currency, on=r.on, buy=r.buy, sell=r.sell, unit=r.unit,
                  source=r.source, override_reason=r.override_reason)
