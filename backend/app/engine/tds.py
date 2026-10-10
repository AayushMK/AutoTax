"""Monthly TDS: project the year, compute annual tax, spread the unpaid balance.

    projected annual = previous employer + paid periods + this period
                       + full-month recurring pay × shares of the remaining periods
    this period TDS  = (annual tax − TDS already withheld) × share now / (share now + shares remaining)

A "share" is the part of a full month a period pays: 1 for a normal month, 16/31 for a split
July or a mid-month joiner. The last period of service takes the exact remainder, so the year's
TDS sums to the annual liability even when FX rates, salary or bonuses change mid-year.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

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
    PriorEmployment,
)
from .money import ZERO, apply_fraction, fmt, round_money
from .rules import RuleSet
from .trace import Trace

MAX_PERIODS = 13


class PayrollSequenceError(ValueError):
    pass


def compute_month(
    profile: EmployeeProfile,
    reliefs: AnnualReliefs,
    rules: RuleSet,
    history: list[PostedMonth],
    current: MonthInput,
    fx: FxTable | None = None,
    prior: PriorEmployment | None = None,
) -> MonthResult:
    _check_sequence(profile, history, current)
    fx = fx or FxTable()
    prior = prior or PriorEmployment()
    t = Trace()
    share = current.share
    later = current.remaining_shares
    if later is None:
        later = tuple(Fraction(1) for _ in range(profile.last_month - current.month))
    later_total = sum(later, Fraction(0))
    partial = share != 1

    # This period's pay in NPR. Recurring lines are monthly amounts, prorated by the share.
    gross = basic = recurring_full = recurring_basic_full = ZERO
    for line in current.lines:
        npr = to_npr(line, fx, rules, t)
        if line.recurring:
            recurring_full += npr
            if line.kind == IncomeKind.BASIC:
                recurring_basic_full += npr
            if partial:
                full, npr = npr, apply_fraction(npr, share)
                t.add(f"{line.kind} for part of the month", npr, f"{fmt(full)} × {share} ({current.share_note or share})")
        gross += npr
        if line.kind == IncomeKind.BASIC:
            basic += npr
    t.add(f"Period {current.month} gross income (NPR)", gross)

    ssf_ee, ssf_er = _ssf(profile, basic, rules)
    if profile.ssf_enrolled:
        t.add("SSF employee contribution", ssf_ee, f"{fmt(basic)} × {rules.value('ssf.employee_rate')}", rules.cite("ssf.employee_rate"))
        t.add("SSF employer contribution", ssf_er, f"{fmt(basic)} × {rules.value('ssf.employer_rate')}", rules.cite("ssf.employer_rate"))

    other_now = apply_fraction(current.other_retirement, share)
    proj_ssf_ee, proj_ssf_er = _ssf(profile, apply_fraction(recurring_basic_full, later_total), rules)
    proj_other = apply_fraction(current.other_retirement, later_total) if current.retirement_recurring else ZERO

    def figures_with(cit_total: Decimal) -> AnnualFigures:
        return AnnualFigures(
            gross_income=prior.income + sum((m.gross_income for m in history), ZERO) + gross
            + apply_fraction(recurring_full, later_total),
            basic=sum((m.basic for m in history), ZERO) + basic + apply_fraction(recurring_basic_full, later_total),
            ssf_employee=sum((m.ssf_employee for m in history), ZERO) + ssf_ee + proj_ssf_ee,
            ssf_employer=sum((m.ssf_employer for m in history), ZERO) + ssf_er + proj_ssf_er,
            cit=cit_total,
            other_retirement=prior.retirement + sum((m.other_retirement for m in history), ZERO) + other_now + proj_other,
        )

    if prior.income or prior.retirement or prior.tds:
        t.add("Previous employer this year: income", prior.income,
              f"retirement contributions {fmt(prior.retirement)}, TDS {fmt(prior.tds)} (salary certificate)")

    # CIT for this period, and the year's projected CIT.
    cit_paid = sum((m.cit for m in history), ZERO)
    if current.cit_mode == "fill_cap":
        base = figures_with(ZERO)
        assessable = base.gross_income + (base.ssf_employer if rules.value("ssf.employer_contribution_taxable") else ZERO)
        limit = min(rules.dec("retirement.cap_amount"), apply_fraction(assessable, rules.frac("retirement.cap_fraction")))
        others = base.ssf_employee + base.ssf_employer + base.other_retirement
        allowable = max(ZERO, limit - others)
        left = max(ZERO, allowable - cit_paid)
        cit_now = left if later_total == 0 else _spread(left, share, later_total)
        cit_year = cit_paid + left
        t.add("CIT this period (fills the retirement limit)", cit_now,
              f"limit {fmt(limit)} − SSF and other funds {fmt(others)} = CIT for the year {fmt(allowable)}; "
              f"deposited {fmt(cit_paid)}, {fmt(left)} left, spread over the remaining periods",
              rules.cite("retirement.cap_amount"))
    else:
        cit_now = apply_fraction(current.cit, share)
        cit_year = cit_paid + cit_now + (apply_fraction(current.cit, later_total) if current.retirement_recurring else ZERO)
        if partial and current.cit:
            t.add("CIT for part of the month", cit_now, f"{fmt(current.cit)} × {share}")

    figures = figures_with(cit_year)
    t.add(
        "Projected annual gross income",
        figures.gross_income,
        f"{'previous employer ' + fmt(prior.income) + ' + ' if prior.income else ''}"
        f"paid {fmt(sum((m.gross_income for m in history), ZERO) + gross)} + recurring {fmt(recurring_full)} × {fmt_share(later_total)} remaining months",
    )

    annual = compute_annual_tax(profile, figures, reliefs, rules)
    t.extend(annual.trace, prefix="  [annual] ")
    tax_without_cit = compute_annual_tax(profile, figures_with(ZERO), reliefs, rules).total_tax

    withheld = prior.tds + sum((m.tds for m in history), ZERO)
    balance = max(ZERO, annual.total_tax - withheld)
    places = int(rules.value("rounding.tds_places"))
    if not current.withhold_tds and later_total != 0:
        tds = ZERO
        detail = f"not withheld this month{': ' + current.withhold_note if current.withhold_note else ''}; " \
                 f"the year's {fmt(annual.total_tax)} is spread over the months when withholding starts"
    elif later_total == 0:
        tds = round_money(balance, places)
        detail = f"final period: {fmt(annual.total_tax)} − withheld {fmt(withheld)}"
    else:
        tds = _spread(balance, share, later_total, places)
        detail = f"({fmt(annual.total_tax)} − withheld {fmt(withheld)}) × {fmt_share(share)} / {fmt_share(share + later_total)} months"
    if annual.total_tax < withheld:
        detail += f"; OVER-WITHHELD by {fmt(withheld - annual.total_tax)} (settle at year end)"
    t.add("TDS this month", tds, detail, rules.cite("rounding.tds_places"))

    net = gross - ssf_ee - cit_now - other_now - tds
    t.add("Net pay", net, f"{fmt(gross)} − SSF {fmt(ssf_ee)} − CIT {fmt(cit_now)} − other {fmt(other_now)} − TDS {fmt(tds)}")

    posted = PostedMonth(
        month=current.month, gross_income=gross, basic=basic, recurring_income=recurring_full,
        recurring_basic=recurring_basic_full, ssf_employee=ssf_ee, ssf_employer=ssf_er, cit=cit_now,
        other_retirement=other_now, tds=tds,
    )
    return MonthResult(posted=posted, tds=tds, net_pay=net, projected_annual=figures, annual=annual, trace=t,
                       tax_without_cit=tax_without_cit)


def _spread(amount: Decimal, share: Fraction, later: Fraction, places: int = 2) -> Decimal:
    """This period's part of `amount`, in proportion to its share of the periods left (incl. this one)."""
    part = amount * share.numerator * later.denominator / (share.numerator * later.denominator + later.numerator * share.denominator)
    return part.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def fmt_share(f: Fraction) -> str:
    return str(f.numerator) if f.denominator == 1 else f"{float(f):.2f}"


def _ssf(profile: EmployeeProfile, basic: Decimal, rules: RuleSet) -> tuple[Decimal, Decimal]:
    if not profile.ssf_enrolled:
        return ZERO, ZERO
    return (
        round_money(basic * rules.dec("ssf.employee_rate")),
        round_money(basic * rules.dec("ssf.employer_rate")),
    )


def _check_sequence(profile: EmployeeProfile, history: list[PostedMonth], current: MonthInput) -> None:
    if not 1 <= profile.first_month <= profile.last_month <= MAX_PERIODS:
        raise PayrollSequenceError(f"invalid service periods {profile.first_month}..{profile.last_month}")
    if not profile.first_month <= current.month <= profile.last_month:
        raise PayrollSequenceError(f"period {current.month} outside service periods {profile.first_month}..{profile.last_month}")
    if not 0 < current.share <= 1:
        raise PayrollSequenceError(f"share {current.share} must be in (0, 1]")
    months = [m.month for m in history]
    if months != sorted(set(months)) or (months and months[-1] >= current.month):
        raise PayrollSequenceError(f"history periods {months} must be strictly increasing and before {current.month}")
