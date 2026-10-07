from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.engine import (
    AnnualFigures,
    AnnualReliefs,
    EmployeeProfile,
    FxRate,
    FxRateMissing,
    FxTable,
    IncomeKind,
    IncomeLine,
    MonthInput,
    PayrollSequenceError,
    compute_annual_tax,
    compute_month,
)
from app.engine.money import D, ZERO

FY_START = date(2026, 7, 17)


def run_year(profile, rules, months: dict[int, MonthInput], fx=None, reliefs=AnnualReliefs()):
    history, results = [], []
    for m in range(profile.first_month, profile.last_month + 1):
        res = compute_month(profile, reliefs, rules, history, months[m], fx)
        history.append(res.posted)
        results.append(res)
    return history, results


def actual_annual(profile, rules, history, reliefs=AnnualReliefs()):
    s = lambda f: sum((getattr(m, f) for m in history), ZERO)  # noqa: E731
    figs = AnnualFigures(
        gross_income=s("gross_income"),
        basic=s("basic"),
        ssf_employee=s("ssf_employee"),
        ssf_employer=s("ssf_employer"),
        cit=s("cit"),
        other_retirement=s("other_retirement"),
    )
    return compute_annual_tax(profile, figs, reliefs, rules)


def npr_month(m, basic, allowance=ZERO, bonus=ZERO, cit=ZERO):
    lines = [IncomeLine(IncomeKind.BASIC, D(basic))]
    if allowance:
        lines.append(IncomeLine(IncomeKind.ALLOWANCE, D(allowance)))
    if bonus:
        lines.append(IncomeLine(IncomeKind.BONUS, D(bonus), recurring=False))
    return MonthInput(month=m, lines=lines, cit=D(cit))


def test_stable_salary_even_split(fy8384):
    p = EmployeeProfile("e1")
    history, results = run_year(p, fy8384, {m: npr_month(m, 100000) for m in range(1, 13)})
    assert all(r.tds == D(2500) for r in results)
    assert sum(m.tds for m in history) == D(30000)


def test_bonus_month_and_ssf_sum_matches_annual(fy8384):
    p = EmployeeProfile("e2", ssf_enrolled=True)
    months = {m: npr_month(m, 120000, allowance=30000, cit=10000) for m in range(1, 13)}
    months[3] = npr_month(3, 120000, allowance=30000, bonus=150000, cit=10000)  # Dashain bonus
    history, results = run_year(p, fy8384, months)
    final = actual_annual(p, fy8384, history)
    assert sum(m.tds for m in history) == final.total_tax
    assert results[0].posted.ssf_employee == D("13200.00")
    assert results[0].net_pay == D(150000) - D("13200") - D(10000) - results[0].tds


def test_mid_year_joiner(fy8384):
    p = EmployeeProfile("e3", first_month=7)
    history, results = run_year(p, fy8384, {m: npr_month(m, 250000) for m in range(7, 13)})
    # 6 × 250,000 = 1,500,000 → 10,000 + 50,000 = 60,000 → 10,000/month
    assert [r.tds for r in results] == [D(10000)] * 6


def test_usd_salary_with_moving_rate(fy8384):
    p = EmployeeProfile("e4")
    fx = FxTable()
    months = {}
    for m in range(1, 13):
        pay = FY_START + timedelta(days=30 * m - 1)
        fx.add(FxRate("USD", pay, buy=D("150") + m, sell=D("150.60") + m))
        months[m] = MonthInput(m, [IncomeLine(IncomeKind.BASIC, D(1500), "USD", pay)])
    history, results = run_year(p, fy8384, months, fx)
    assert history[0].gross_income == D(1500) * D(151)
    final = actual_annual(p, fy8384, history)
    assert sum(m.tds for m in history) == final.total_tax
    assert "FX basic USD" in str(results[0].trace)


def test_fx_falls_back_to_prior_published_rate(fy8384):
    fx = FxTable([FxRate("USD", date(2026, 8, 14), D("153.01"), D("153.61"))])
    p = EmployeeProfile("e5")
    res = compute_month(p, AnnualReliefs(), fy8384, [], MonthInput(1, [IncomeLine(IncomeKind.BASIC, D(1000), "USD", date(2026, 8, 16))]), fx)
    assert res.posted.gross_income == D("153010.00")
    assert "nearest prior" in str(res.trace)
    with pytest.raises(FxRateMissing):
        compute_month(p, AnnualReliefs(), fy8384, [], MonthInput(1, [IncomeLine(IncomeKind.BASIC, D(1000), "USD", date(2026, 9, 30))]), fx)


def test_manual_override_beats_published(fy8384):
    fx = FxTable()
    fx.add(FxRate("USD", date(2026, 8, 14), D("140"), D("141"), override_reason="Bank credit advice #123"))
    fx.add(FxRate("USD", date(2026, 8, 14), D("153.01"), D("153.61")))
    assert fx.lookup("USD", date(2026, 8, 14)).buy == D("140")


def test_sequence_errors(fy8384):
    p = EmployeeProfile("e6")
    first = compute_month(p, AnnualReliefs(), fy8384, [], npr_month(1, 100000)).posted
    with pytest.raises(PayrollSequenceError):
        compute_month(p, AnnualReliefs(), fy8384, [first], npr_month(1, 100000))
    with pytest.raises(PayrollSequenceError):
        compute_month(EmployeeProfile("e7", last_month=6), AnnualReliefs(), fy8384, [], npr_month(7, 100000))


@settings(max_examples=150, deadline=None)
@given(
    salaries=st.lists(st.integers(min_value=0, max_value=1_500_000), min_size=12, max_size=12),
    ssf=st.booleans(),
    female=st.booleans(),
)
def test_property_year_tds_reconciles(fy8384, salaries, ssf, female):
    p = EmployeeProfile("p", ssf_enrolled=ssf, gender="female" if female else "male")
    history, results = run_year(p, fy8384, {m: npr_month(m, salaries[m - 1]) for m in range(1, 13)})
    final = actual_annual(p, fy8384, history)
    assert all(r.tds >= 0 for r in results)
    assert final.total_tax >= 0
    assert final.retirement_deduction <= fy8384.dec("retirement.cap_amount")
    withheld_before_last = sum((m.tds for m in history[:-1]), ZERO)
    if withheld_before_last <= final.total_tax:
        assert sum(m.tds for m in history) == final.total_tax
    else:  # income fell late in the year: over-withheld, settled via annual return/refund
        assert results[-1].tds == 0
