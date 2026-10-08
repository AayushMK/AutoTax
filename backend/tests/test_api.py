"""End-to-end API tests against Postgres (autotax_test)."""

from datetime import date
from decimal import Decimal

import nepali_datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import Base, SessionLocal, engine
from app.engine.fx import FxRate
from app.main import app
from app.services import fx_store
from app.services.calendar import fiscal_year_of, fy_month

SHRAWAN_15 = nepali_datetime.date(2083, 4, 15).to_datetime_date()  # FY 2083/84 month 1
BHADRA_15 = nepali_datetime.date(2083, 5, 15).to_datetime_date()  # month 2
ASHWIN_15 = nepali_datetime.date(2083, 6, 15).to_datetime_date()  # month 3


@pytest.fixture(scope="session", autouse=True)
def schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def clean():
    with engine.begin() as c:
        c.execute(text("TRUNCATE " + ", ".join(t.name for t in Base.metadata.sorted_tables) + " RESTART IDENTITY CASCADE"))


@pytest.fixture
def client():
    return TestClient(app)


def signup(client, email="owner@acme.np", company="Acme Pvt Ltd"):
    r = client.post("/api/auth/signup", json={"email": email, "name": "Owner", "password": "s3cret-pass", "company_name": company})
    assert r.status_code == 201, r.text
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    cid = client.get("/api/auth/me", headers=h).json()["memberships"][0]["company_id"]
    return h, cid


def add_employee(client, h, cid, code, joined=date(2025, 1, 1), basic="100000", currency="NPR", ssf=False, cit="0", gender="male"):
    e = client.post(f"/api/companies/{cid}/employees", headers=h, json={"code": code, "name": f"Emp {code}", "joined_on": str(joined)})
    assert e.status_code == 201, e.text
    eid = e.json()["id"]
    r = client.put(f"/api/companies/{cid}/employees/{eid}/tax-profiles/2083-84", headers=h, json={"ssf_enrolled": ssf, "gender": gender})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/companies/{cid}/employees/{eid}/salary-structures", headers=h, json={
        "effective_from": str(joined), "components": [{"kind": "basic", "amount": basic, "currency": currency}], "cit_monthly": cit,
    })
    assert r.status_code == 201, r.text
    return eid


def seed_usd(rate="150.00", on=None):
    on = on or SHRAWAN_15
    with SessionLocal() as db:
        fx_store.sync_nrb(db, on, on, {"USD"}, fetch=lambda s, e, c: [FxRate("USD", on, Decimal(rate), Decimal(rate) + Decimal("0.60"))])
        db.commit()


def test_calendar_assumptions():
    assert fiscal_year_of(SHRAWAN_15) == "2083/84" and fy_month(SHRAWAN_15) == 1 and fy_month(BHADRA_15) == 2


def test_signup_me_and_isolation(client):
    h, cid = signup(client)
    me = client.get("/api/auth/me", headers=h).json()
    assert me["memberships"][0]["role"] == "admin"
    h2, cid2 = signup(client, "other@beta.np", "Beta")
    assert client.get(f"/api/companies/{cid}/employees", headers=h2).status_code == 404
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "owner@acme.np", "password": "wrong-pass"}).status_code == 401


def test_full_payroll_lifecycle(client):
    h, cid = signup(client)
    a = add_employee(client, h, cid, "E001", basic="100000")  # NPR, 12 lakh/yr → 30,000 tax → 2,500/month
    b = add_employee(client, h, cid, "E002", basic="1500", currency="USD", ssf=True, cit="5000", gender="female")
    seed_usd("150.00")

    run = client.post(f"/api/companies/{cid}/payroll-runs", headers=h, json={"payment_date": str(SHRAWAN_15)}).json()
    assert (run["fiscal_year"], run["month"], run["month_label"]) == ("2083/84", 1, "Shrawan 2083")
    r = client.post(f"/api/companies/{cid}/payroll-runs/{run['id']}/compute", headers=h)
    assert r.status_code == 200, r.text
    slips = {p["employee_code"]: p for p in r.json()["payslips"]}
    assert Decimal(slips["E001"]["tds"]) == Decimal("2500.00")
    assert Decimal(slips["E002"]["gross"]) == Decimal("225000.00")  # 1500 × 150 (NRB buying)
    assert Decimal(slips["E002"]["ssf_employee"]) == Decimal("24750.00")
    assert r.json()["rule_set"] == "NP/2083/84/v1"

    detail = client.get(f"/api/companies/{cid}/payroll-runs/{run['id']}/payslips/{slips['E002']['id']}", headers=h).json()
    assert detail["inputs"]["fx"]["USD"]["buy"] == "150.000000"
    assert any("FX basic USD" in s["label"] for s in detail["trace"])

    # Unverified rules need an explicit, recorded acknowledgement.
    r = client.post(f"/api/companies/{cid}/payroll-runs/{run['id']}/finalize", headers=h, json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "rules_unverified"
    r = client.post(f"/api/companies/{cid}/payroll-runs/{run['id']}/finalize", headers=h, json={"acknowledge_unverified": True})
    assert r.status_code == 200 and r.json()["status"] == "finalized"
    assert r.json()["acknowledged_unverified"]

    # Frozen.
    assert client.post(f"/api/companies/{cid}/payroll-runs/{run['id']}/compute", headers=h).status_code == 422
    assert client.delete(f"/api/companies/{cid}/payroll-runs/{run['id']}", headers=h).status_code == 409

    # Month 2 builds on month 1; one-off Dashain bonus for E001.
    seed_usd("152.00", BHADRA_15)
    run2 = client.post(f"/api/companies/{cid}/payroll-runs", headers=h, json={"payment_date": str(BHADRA_15)}).json()
    client.post(f"/api/companies/{cid}/payroll-runs/{run2['id']}/adjustments", headers=h,
                json={"employee_id": a, "kind": "dashain", "amount": "100000"})
    r = client.post(f"/api/companies/{cid}/payroll-runs/{run2['id']}/finalize", headers=h, json={"acknowledge_unverified": True})
    assert r.status_code == 200, r.text
    s2 = {p["employee_code"]: p for p in r.json()["payslips"]}
    # E001: projected 100k×12 + 100k bonus = 13L → tax 10,000 + 30,000 = 40,000; 2,500 withheld; 37,500 / 11 months
    assert Decimal(s2["E001"]["tds"]) == (Decimal(37500) / 11).quantize(Decimal("0.01"))
    assert Decimal(s2["E002"]["gross"]) == Decimal("228000.00")

    csv_text = client.get(f"/api/companies/{cid}/payroll-runs/{run2['id']}/tds.csv", headers=h).text
    assert csv_text.splitlines()[0].startswith("employee_code") and len(csv_text.splitlines()) == 3

    actions = [x["action"] for x in client.get(f"/api/companies/{cid}/audit", headers=h).json()]
    assert actions.count("payroll.finalize") == 2 and "fx.override" not in actions


def test_problems_are_listed_and_nothing_is_saved(client):
    h, cid = signup(client)
    add_employee(client, h, cid, "E001")
    e = client.post(f"/api/companies/{cid}/employees", headers=h, json={"code": "E002", "name": "No Profile", "joined_on": "2025-01-01"}).json()
    run = client.post(f"/api/companies/{cid}/payroll-runs", headers=h, json={"payment_date": str(SHRAWAN_15)}).json()
    r = client.post(f"/api/companies/{cid}/payroll-runs/{run['id']}/compute", headers=h)
    assert r.status_code == 422
    assert any("E002" in p and "tax profile" in p for p in r.json()["detail"]["problems"])
    assert client.get(f"/api/companies/{cid}/payroll-runs/{run['id']}", headers=h).json()["payslips"] == []
    assert e["id"]


def test_months_must_be_finalized_in_order(client):
    h, cid = signup(client)
    add_employee(client, h, cid, "E001")
    client.post(f"/api/companies/{cid}/payroll-runs", headers=h, json={"payment_date": str(SHRAWAN_15)})
    run3 = client.post(f"/api/companies/{cid}/payroll-runs", headers=h, json={"payment_date": str(ASHWIN_15)}).json()
    r = client.post(f"/api/companies/{cid}/payroll-runs/{run3['id']}/finalize", headers=h, json={"acknowledge_unverified": True})
    assert r.status_code == 422 and "Shrawan 2083" in r.json()["detail"]["message"]
    dup = client.post(f"/api/companies/{cid}/payroll-runs", headers=h, json={"payment_date": str(SHRAWAN_15)})
    assert dup.status_code == 422


def test_mid_year_joiner_only_in_their_months(client):
    h, cid = signup(client)
    add_employee(client, h, cid, "E001")
    add_employee(client, h, cid, "E009", joined=BHADRA_15)
    run = client.post(f"/api/companies/{cid}/payroll-runs", headers=h, json={"payment_date": str(SHRAWAN_15)}).json()
    r = client.post(f"/api/companies/{cid}/payroll-runs/{run['id']}/compute", headers=h).json()
    assert [p["employee_code"] for p in r["payslips"]] == ["E001"]


def test_fx_override_used_and_audited(client):
    h, cid = signup(client)
    add_employee(client, h, cid, "E002", basic="1000", currency="USD")
    seed_usd("150.00")
    r = client.post(f"/api/companies/{cid}/fx/overrides", headers=h, json={
        "currency": "usd", "on": str(SHRAWAN_15), "buy": "149.10", "sell": "149.70", "reason": "Bank credit advice 4471"})
    assert r.status_code == 201
    run = client.post(f"/api/companies/{cid}/payroll-runs", headers=h, json={"payment_date": str(SHRAWAN_15)}).json()
    slip = client.post(f"/api/companies/{cid}/payroll-runs/{run['id']}/compute", headers=h).json()["payslips"][0]
    assert Decimal(slip["gross"]) == Decimal("149100.00")
    # Another company does not see this override.
    h2, cid2 = signup(client, "x@y.np", "Other")
    rates = client.get(f"/api/companies/{cid2}/fx/rates", headers=h2, params={"currency": "USD", "start": str(SHRAWAN_15), "end": str(SHRAWAN_15)}).json()
    assert [x["source"] for x in rates] == ["NRB"]


def test_roles(client):
    h, cid = signup(client)
    hv, _ = signup(client, "viewer@acme.np", "Viewer Co")
    assert client.post(f"/api/companies/{cid}/members", headers=h, json={"email": "viewer@acme.np", "role": "viewer"}).status_code == 201
    assert client.get(f"/api/companies/{cid}/employees", headers=hv).status_code == 200
    r = client.post(f"/api/companies/{cid}/employees", headers=hv, json={"code": "X", "name": "X", "joined_on": "2025-01-01"})
    assert r.status_code == 403


def test_rules_status(client):
    h, _ = signup(client)
    s = client.get("/api/rules/status", headers=h, params={"on": "2026-10-07"}).json()
    assert s["current"]["version"] == "NP/2083/84/v1" and s["current"]["review_status"] == "draft"
    assert client.get("/api/rules/2083-84", headers=h).json()["params"]["retirement.cap_amount"]["value"] == 500000
