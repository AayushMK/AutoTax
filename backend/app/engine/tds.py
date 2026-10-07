"""Monthly TDS: project the year, compute annual tax, spread the unpaid balance.

    projected annual = actual posted months + this month + recurring items × months left after this one
    this month TDS   = (annual tax − TDS already withheld) / months left including this one

The last month of service takes the exact remainder, so the year's TDS sums to the annual
liability even when FX rates, salary or bonuses change mid-year.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .annual import compute_annual_tax
from .fx import FxTable, to_npr
from .models import (
    AnnualFigures,
    AnnualReliefs,
    EmployeeProfile,
    IncomeKind,
    MonthInput,
    MonthResult,
    PostedMonth,
)
from .money import ZERO, fmt, round_money
from .rules import RuleSet
from .trace import Trace


class PayrollSequenceError(ValueError):
    pass


def compute_month(
    profile: EmployeeProfile,
    reliefs: AnnualReliefs,
    rules: RuleSet,
    history: list[PostedMonth],
    current: MonthInput,
    fx: FxTable | None = None,
) -> MonthResult:
    _check_sequence(profile, history, current)
    fx = fx or FxTable()
    t = Trace()

    # Convert this month's lines to NPR.
    gross = basic = recurring = recurring_basic = ZERO
    for line in current.lines:
        npr = to_npr(line, fx, rules, t)
        gross += npr
        if line.kind == IncomeKind.BASIC:
            basic += npr
        if line.recurring:
            recurring += npr
            if line.kind == IncomeKind.BASIC:
                recurring_basic += npr
    t.add(f"Month {current.month} gross income (NPR)", gross)

    ssf_ee, ssf_er = _ssf(profile, basic, rules)
    if profile.ssf_enrolled:
        t.add("SSF employee contribution", ssf_ee, f"{fmt(basic)} × {rules.value('ssf.employee_rate')}", rules.cite("ssf.employee_rate"))
        t.add("SSF employer contribution", ssf_er, f"{fmt(basic)} × {rules.value('ssf.employer_rate')}", rules.cite("ssf.employer_rate"))

    posted_partial = PostedMonth(
        month=current.month,
        gross_income=gross,
        basic=basic,
        recurring_income=recurring,
        recurring_basic=recurring_basic,
        ssf_employee=ssf_ee,
        ssf_employer=ssf_er,
        cit=current.cit,
        other_retirement=current.other_retirement,
        tds=ZERO,
    )

    # Project the year.
    months_after = profile.last_month - current.month
    proj_ssf_ee, proj_ssf_er = _ssf(profile, recurring_basic, rules)
    retire_recurring = current.retirement_recurring
    actual = history + [posted_partial]
    figures = AnnualFigures(
        gross_income=sum((m.gross_income for m in actual), ZERO) + recurring * months_after,
        basic=sum((m.basic for m in actual), ZERO) + recurring_basic * months_after,
        ssf_employee=sum((m.ssf_employee for m in actual), ZERO) + proj_ssf_ee * months_after,
        ssf_employer=sum((m.ssf_employer for m in actual), ZERO) + proj_ssf_er * months_after,
        cit=sum((m.cit for m in actual), ZERO) + (current.cit * months_after if retire_recurring else ZERO),
        other_retirement=sum((m.other_retirement for m in actual), ZERO)
        + (current.other_retirement * months_after if retire_recurring else ZERO),
    )
    t.add(
        "Projected annual gross income",
        figures.gross_income,
        f"actual months {fmt(sum((m.gross_income for m in actual), ZERO))} + recurring {fmt(recurring)} × {months_after} remaining",
    )

    annual = compute_annual_tax(profile, figures, reliefs, rules)
    t.extend(annual.trace, prefix="  [annual] ")

    withheld = sum((m.tds for m in history), ZERO)
    months_left = profile.last_month - current.month + 1
    balance = max(ZERO, annual.total_tax - withheld)
    places = int(rules.value("rounding.tds_places"))
    if months_left == 1:
        tds = round_money(balance, places)
        detail = f"final month: {fmt(annual.total_tax)} − withheld {fmt(withheld)}"
    else:
        tds = (balance / months_left).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
        detail = f"({fmt(annual.total_tax)} − withheld {fmt(withheld)}) / {months_left} months"
    if annual.total_tax < withheld:
        detail += f"; OVER-WITHHELD by {fmt(withheld - annual.total_tax)} (settle at year end)"
    t.add("TDS this month", tds, detail, rules.cite("rounding.tds_places"))

    net = gross - ssf_ee - current.cit - current.other_retirement - tds
    t.add("Net pay", net, f"{fmt(gross)} − SSF {fmt(ssf_ee)} − CIT {fmt(current.cit)} − other {fmt(current.other_retirement)} − TDS {fmt(tds)}")

    posted = PostedMonth(**{**posted_partial.__dict__, "tds": tds})
    return MonthResult(posted=posted, tds=tds, net_pay=net, projected_annual=figures, annual=annual, trace=t)


def _ssf(profile: EmployeeProfile, basic: Decimal, rules: RuleSet) -> tuple[Decimal, Decimal]:
    if not profile.ssf_enrolled:
        return ZERO, ZERO
    return (
        round_money(basic * rules.dec("ssf.employee_rate")),
        round_money(basic * rules.dec("ssf.employer_rate")),
    )


def _check_sequence(profile: EmployeeProfile, history: list[PostedMonth], current: MonthInput) -> None:
    if not 1 <= profile.first_month <= profile.last_month <= 12:
        raise PayrollSequenceError(f"invalid service months {profile.first_month}..{profile.last_month}")
    if not profile.first_month <= current.month <= profile.last_month:
        raise PayrollSequenceError(f"month {current.month} outside service months {profile.first_month}..{profile.last_month}")
    months = [m.month for m in history]
    if months != sorted(set(months)) or (months and months[-1] >= current.month):
        raise PayrollSequenceError(f"history months {months} must be strictly increasing and before {current.month}")
