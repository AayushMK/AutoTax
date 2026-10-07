from datetime import date

import httpx
import pytest
import respx
import yaml

from app.engine.money import D
from app.engine.rules import RULES_DIR, RuleFileError, load_all, load_rule_file, rules_for_date
from app.fx.nrb import NRB_URL, fetch_rates


def test_every_rule_file_loads_and_years_do_not_overlap():
    sets = load_all()
    assert [r.fiscal_year for r in sets] == ["2082/83", "2083/84"]
    for a, b in zip(sets, sets[1:]):
        assert a.effective_to < b.effective_from


def test_rules_for_date():
    assert rules_for_date(date(2026, 7, 16)).fiscal_year == "2082/83"
    assert rules_for_date(date(2026, 7, 17)).fiscal_year == "2083/84"
    with pytest.raises(RuleFileError):
        rules_for_date(date(2020, 1, 1))


def _mutate(tmp_path, fn):
    data = yaml.safe_load((RULES_DIR / "np" / "2083-84.yaml").read_text())
    fn(data)
    p = tmp_path / "x.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True))
    return p


def test_uncited_param_rejected(tmp_path):
    p = _mutate(tmp_path, lambda d: d["params"]["insurance.life_cap"].pop("ref"))
    with pytest.raises(RuleFileError):
        load_rule_file(p)


def test_unknown_source_rejected(tmp_path):
    p = _mutate(tmp_path, lambda d: d["params"]["insurance.life_cap"].update(src="blog"))
    with pytest.raises(RuleFileError):
        load_rule_file(p)


def test_missing_required_param_rejected(tmp_path):
    p = _mutate(tmp_path, lambda d: d["params"].pop("nonresident.flat_rate"))
    with pytest.raises(RuleFileError):
        load_rule_file(p)


@respx.mock
def test_nrb_fetch_paginates_and_respects_units():
    def page(n, pages, day):
        return {
            "status": {"code": 200},
            "data": {"payload": [{"date": day, "rates": [
                {"currency": {"iso3": "USD", "unit": 1}, "buy": "153.01", "sell": "153.61"},
                {"currency": {"iso3": "INR", "unit": 100}, "buy": "160.00", "sell": "160.15"},
            ]}]},
            "pagination": {"page": n, "pages": pages},
        }

    route = respx.get(NRB_URL).mock(side_effect=[
        httpx.Response(200, json=page(1, 2, "2026-09-28")),
        httpx.Response(200, json=page(2, 2, "2026-09-29")),
    ])
    rates = fetch_rates(date(2026, 9, 28), date(2026, 9, 29), {"USD", "INR"})
    assert route.call_count == 2
    inr = next(r for r in rates if r.currency == "INR")
    assert inr.per_unit("buying") == D("1.6")
    assert {r.on for r in rates} == {date(2026, 9, 28), date(2026, 9, 29)}
