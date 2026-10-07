from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from app.engine.gate import budget_season_alert
from app.engine.rules import RuleFileError, load_all, rules_for_date, verify_source_hashes
from app.models import User
from app.security import current_user

router = APIRouter(prefix="/rules", tags=["rules"])


def _summary(rs) -> dict:
    return {
        "version": rs.version_id, "fiscal_year": rs.fiscal_year, "effective_from": rs.effective_from,
        "effective_to": rs.effective_to, "review_status": rs.raw.review.status,
        "unverified_params": rs.unreviewed_params(),
    }


@router.get("/status")
def status_(on: date | None = None, _: User = Depends(current_user)):
    on = on or date.today()
    try:
        rs = rules_for_date(on)
        current = _summary(rs) | {"sources": verify_source_hashes(rs)}
    except RuleFileError:
        current = None
    return {"date": on, "current": current, "alert": budget_season_alert(on), "all": [_summary(r) for r in load_all()]}


@router.get("/{fy}")
def rule_set(fy: str, _: User = Depends(current_user)):
    fiscal_year = fy.replace("-", "/")
    matches = [r for r in load_all() if r.fiscal_year == fiscal_year]
    if not matches:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no rules for {fiscal_year}")
    rs = max(matches, key=lambda r: r.raw.version)
    return _summary(rs) | {
        "sources": {k: s.model_dump() for k, s in rs.raw.sources.items()},
        "params": {k: p.model_dump() for k, p in rs.raw.params.items()},
    }
