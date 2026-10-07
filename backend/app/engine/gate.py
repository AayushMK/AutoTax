"""Safety gates applied before a payroll run is finalized, and calendar alerts.

- No rule file covers the payroll date            -> blocked (RuleCoverageError)
- Rule file has unverified params / draft review   -> blocked unless explicitly acknowledged
- An archived source PDF no longer matches its hash -> blocked
- Budget season (Jestha 15 → Shrawan 1) without next FY's rules -> alert
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import nepali_datetime

from .rules import RULES_DIR, RuleFileError, RuleSet, load_all, rules_for_date, verify_source_hashes

BUDGET_DAY_BS = (2, 15)  # Jestha 15: budget presented (Constitution Art. 119(3))
FY_START_BS = (4, 1)  # Shrawan 1


class RuleCoverageError(RuntimeError):
    pass


class UnverifiedRulesError(RuntimeError):
    def __init__(self, rule_set: RuleSet, params: list[str]):
        self.rule_set = rule_set
        self.params = params
        super().__init__(
            f"{rule_set.version_id} is '{rule_set.raw.review.status}' with {len(params)} unverified params: "
            f"{', '.join(params[:6])}{'…' if len(params) > 6 else ''}. Pass acknowledge_unverified=True to proceed."
        )


class SourceIntegrityError(RuntimeError):
    pass


@dataclass
class GateResult:
    rule_set: RuleSet
    warnings: list[str] = field(default_factory=list)
    acknowledged_unverified: list[str] = field(default_factory=list)  # store in the audit log


def check_payroll_allowed(on: date, acknowledge_unverified: bool = False, rules_dir=RULES_DIR) -> GateResult:
    try:
        rs = rules_for_date(on, rules_dir=rules_dir)
    except RuleFileError as e:
        raise RuleCoverageError(f"Payroll for {on} blocked: {e}. Add the Finance Act rule file first.") from e

    bad = [k for k, ok in verify_source_hashes(rs, rules_dir / "sources").items() if ok is False]
    if bad:
        raise SourceIntegrityError(f"{rs.version_id}: archived source(s) {bad} missing or hash mismatch")

    result = GateResult(rs)
    unverified = rs.unreviewed_params()
    if unverified or rs.raw.review.status != "ca_reviewed":
        if not acknowledge_unverified:
            raise UnverifiedRulesError(rs, unverified)
        result.acknowledged_unverified = unverified
        result.warnings.append(f"Proceeding with unverified rules {rs.version_id} ({len(unverified)} params)")
    alert = budget_season_alert(on, rules_dir=rules_dir)
    if alert:
        result.warnings.append(alert)
    return result


def fy_start_ad(bs_year: int) -> date:
    return nepali_datetime.date(bs_year, *FY_START_BS).to_datetime_date()


def budget_season_alert(today: date, rules_dir=RULES_DIR) -> str | None:
    """Warn from Jestha 15 until next FY's rules exist; error once the current FY is uncovered."""
    sets = load_all(rules_dir=rules_dir)
    covered = lambda d: any(rs.effective_from <= d <= rs.effective_to for rs in sets)  # noqa: E731
    if not covered(today):
        return f"CRITICAL: no rule file covers today ({today}). Payroll is blocked."
    bs = nepali_datetime.date.from_datetime_date(today)
    next_fy_start = fy_start_ad(bs.year if (bs.month, bs.day) < FY_START_BS else bs.year + 1)
    budget_day = nepali_datetime.date(nepali_datetime.date.from_datetime_date(next_fy_start).year, *BUDGET_DAY_BS).to_datetime_date()
    if budget_day <= today < next_fy_start and not covered(next_fy_start):
        days = (next_fy_start - today).days
        return (
            f"Budget season: the Finance Act for the FY starting {next_fy_start} is due; no rule file covers it yet "
            f"({days} days left)."
        )
    return None
