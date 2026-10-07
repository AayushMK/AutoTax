"""Annual salary tax for one employee, per the rule file. Pure function."""

from __future__ import annotations

from decimal import Decimal

from .models import AnnualFigures, AnnualReliefs, AnnualTaxResult, EmployeeProfile
from .money import ZERO, apply_fraction, fmt, round_money
from .rules import RuleSet, Slab
from .trace import Trace


def compute_annual_tax(
    profile: EmployeeProfile,
    figures: AnnualFigures,
    reliefs: AnnualReliefs,
    rules: RuleSet,
) -> AnnualTaxResult:
    t = Trace()
    gross = t.add("Gross employment income", figures.gross_income)

    employer_ssf = ZERO
    if rules.value("ssf.employer_contribution_taxable") and figures.ssf_employer:
        employer_ssf = t.add(
            "Add: employer SSF contribution", figures.ssf_employer, citation=rules.cite("ssf.employer_contribution_taxable")
        )
    assessable = t.add("Assessable income", gross + employer_ssf, f"{fmt(gross)} + {fmt(employer_ssf)}")

    if not profile.resident:
        return _non_resident(assessable, rules, t)

    # 1. Retirement contributions (Sec 63): lesser of actual, 1/3 of assessable, cap.
    contributions = figures.ssf_employee + figures.ssf_employer + figures.cit + figures.other_retirement
    third = apply_fraction(assessable, rules.frac("retirement.cap_fraction"))
    cap = rules.dec("retirement.cap_amount")
    retirement = min(contributions, third, cap)
    t.add(
        "Less: retirement contribution deduction",
        retirement,
        f"min(actual {fmt(contributions)} [SSF {fmt(figures.ssf_employee + figures.ssf_employer)}, "
        f"CIT {fmt(figures.cit)}, other {fmt(figures.other_retirement)}]; "
        f"{rules.value('retirement.cap_fraction')} of assessable {fmt(third)}; cap {fmt(cap)})",
        rules.cite("retirement.cap_amount"),
    )
    remaining = assessable - retirement

    # 2. Remote area allowance deduction.
    remote = ZERO
    if profile.remote_area:
        remote = min(Decimal(rules.value("remote_area.caps")[profile.remote_area]), remaining)
        t.add(f"Less: remote area deduction (category {profile.remote_area})", remote, citation=rules.cite("remote_area.caps"))
    remaining -= remote

    # 3. Donations (Sec 12): lesser of actual, 5% of adjusted taxable income, cap.
    donation = ZERO
    if reliefs.donation:
        pct = apply_fraction(remaining, rules.frac("donation.cap_fraction"))
        donation = min(reliefs.donation, pct, rules.dec("donation.cap_amount"))
        t.add(
            "Less: donation",
            donation,
            f"min(actual {fmt(reliefs.donation)}; {fmt(pct)}; cap {fmt(rules.dec('donation.cap_amount'))})",
            rules.cite("donation.cap_amount"),
        )
    remaining -= donation

    # 4. Insurance premiums.
    insurance = ZERO
    for label, paid, key in (
        ("life insurance premium", reliefs.life_insurance_premium, "insurance.life_cap"),
        ("health insurance premium", reliefs.health_insurance_premium, "insurance.health_cap"),
        ("private building insurance premium", reliefs.building_insurance_premium, "insurance.building_cap"),
    ):
        if paid:
            allowed = min(paid, rules.dec(key))
            t.add(f"Less: {label}", allowed, f"min(paid {fmt(paid)}; cap {fmt(rules.dec(key))})", rules.cite(key))
            insurance += allowed

    taxable = t.add("Taxable income", max(ZERO, remaining - insurance))

    # 5. Slab tax.
    sst, income_tax = _slab_tax(profile, taxable, rules, t)
    gross_tax = sst + income_tax

    # 6. Female rebate.
    rebate = ZERO
    if _female_rebate_eligible(profile, rules):
        rebate = round_money(gross_tax * rules.dec("female_rebate.rate"))
        t.add("Less: female taxpayer rebate", rebate, f"{fmt(gross_tax)} × {rules.value('female_rebate.rate')}", rules.cite("female_rebate.rate"))

    total = t.add("Annual tax liability", gross_tax - rebate)
    return AnnualTaxResult(
        assessable_income=assessable,
        retirement_deduction=retirement,
        remote_area_deduction=remote,
        insurance_deduction=insurance,
        donation_deduction=donation,
        taxable_income=taxable,
        sst=sst,
        income_tax=income_tax,
        rebate=rebate,
        total_tax=total,
        rule_set=rules.version_id,
        trace=t,
    )


def _non_resident(assessable: Decimal, rules: RuleSet, t: Trace) -> AnnualTaxResult:
    rate = rules.dec("nonresident.flat_rate")
    tax = round_money(assessable * rate)
    t.add("Non-resident flat tax", tax, f"{fmt(assessable)} × {rate}", rules.cite("nonresident.flat_rate"))
    t.add("Annual tax liability", tax)
    return AnnualTaxResult(
        assessable_income=assessable,
        retirement_deduction=ZERO,
        remote_area_deduction=ZERO,
        insurance_deduction=ZERO,
        donation_deduction=ZERO,
        taxable_income=assessable,
        sst=ZERO,
        income_tax=tax,
        rebate=ZERO,
        total_tax=tax,
        rule_set=rules.version_id,
        trace=t,
    )


def _slab_tax(profile: EmployeeProfile, taxable: Decimal, rules: RuleSet, t: Trace) -> tuple[Decimal, Decimal]:
    key = f"resident.slabs.{profile.filing}"
    slabs: list[Slab] = list(rules.slabs(profile.filing))
    if profile.disabled:
        inc = rules.dec("resident.disability_first_slab_increase")
        first = slabs[0]
        slabs[0] = Slab(round_money(first.width * (1 + inc)), first.rate, first.sst)
        t.add("First slab widened (disability)", slabs[0].width, f"{fmt(first.width)} × (1 + {inc})", rules.cite("resident.disability_first_slab_increase"))

    sst_waived = (profile.ssf_enrolled and "ssf" in rules.value("resident.sst_waiver_schemes")) or (
        profile.approved_pension and "approved_pension" in rules.value("resident.sst_waiver_schemes")
    )

    sst = income_tax = ZERO
    lower = ZERO
    left = taxable
    for slab in slabs:
        if left <= 0:
            break
        portion = left if slab.width is None else min(left, slab.width)
        upper = "∞" if slab.width is None else fmt(lower + slab.width)
        if slab.sst and sst_waived:
            t.add(f"Slab {fmt(lower)}–{upper} @ 0% (SST waived)", ZERO, f"{fmt(portion)} × 0", rules.cite("resident.sst_waiver_schemes"))
        else:
            tax = round_money(portion * slab.rate)
            t.add(f"Slab {fmt(lower)}–{upper} @ {_pct(slab.rate)}%", tax, f"{fmt(portion)} × {slab.rate}", rules.cite(key))
            if slab.sst:
                sst += tax
            else:
                income_tax += tax
        left -= portion
        if slab.width is not None:
            lower += slab.width
    return sst, income_tax


def _pct(rate: Decimal) -> str:
    return f"{rate * 100:.2f}".rstrip("0").rstrip(".")


def _female_rebate_eligible(profile: EmployeeProfile, rules: RuleSet) -> bool:
    if profile.gender != "female" or not profile.income_only_from_employment:
        return False
    if profile.filing == "couple" and rules.value("female_rebate.excluded_if_couple"):
        return False
    return True
