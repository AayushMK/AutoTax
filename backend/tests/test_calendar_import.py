"""English-month calendar, imported months, CIT filled to the cap, previous employer, IRD TDS export."""

from datetime import date
from decimal import Decimal

from .test_api import add_employee, client, clean, schema, signup  # noqa: F401  (fixtures)


def ad_company(client):
    r = client.post("/api/auth/signup", json={"email": "ad@example.com", "name": "HR", "password": "s3cret-pass",
                                              "company_name": "English Months Ltd", "pay_calendar": "ad"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    cid = client.get("/api/auth/me", headers=h).json()["memberships"][0]["company_id"]
    return h, cid


def run(client, h, cid, fy, period, paid):
    r = client.post(f"/api/companies/{cid}/payroll-runs", headers=h, json={"payment_date": paid, "fiscal_year": fy, "period": period})
    assert r.status_code == 201, r.text
    return r.json()


def finalize(client, h, cid, rid):
    r = client.post(f"/api/companies/{cid}/payroll-runs/{rid}/finalize", headers=h, json={"acknowledge_unverified": True})
    assert r.status_code == 200, r.text
    return r.json()


def test_english_months_have_13_periods_with_split_july(client):
    h, cid = ad_company(client)
    ps = client.get(f"/api/companies/{cid}/payroll-runs/periods/2083-84", headers=h).json()
    assert len(ps) == 13 and ps[0]["label"] == "July 2026 (17–31)" and ps[-1]["label"] == "July 2027 (1–16)"
    # Without a period, English-month payroll can't guess which fiscal year a July date belongs to.
    assert client.post(f"/api/companies/{cid}/payroll-runs", headers=h, json={"payment_date": "2026-07-31"}).status_code == 422

    add_employee(client, h, cid, "E001", basic="310000")
    r1 = run(client, h, cid, "2083-84", 1, "2026-07-31")
    slip = finalize(client, h, cid, r1["id"])["payslips"][0]
    assert slip["share"] == "15/31" and Decimal(slip["gross"]) == Decimal("150000.00")  # 3,10,000 × 15/31
    r2 = finalize(client, h, cid, run(client, h, cid, "2083-84", 2, "2026-08-31")["id"])
    assert r2["month_label"] == "August 2026" and Decimal(r2["payslips"][0]["gross"]) == Decimal("310000.00")


def test_calendar_cannot_change_once_payroll_exists(client):
    h, cid = signup(client)
    assert client.put(f"/api/companies/{cid}", headers=h, json={"name": "Acme", "pay_calendar": "ad"}).json()["pay_calendar"] == "ad"
    assert client.put(f"/api/companies/{cid}", headers=h, json={"name": "Acme", "pay_calendar": "bs"}).status_code == 200
    add_employee(client, h, cid, "E001")
    client.post(f"/api/companies/{cid}/payroll-runs", headers=h, json={"payment_date": "2026-08-15"})
    assert client.put(f"/api/companies/{cid}", headers=h, json={"name": "Acme", "pay_calendar": "ad"}).status_code == 409


def test_imported_months_feed_later_tds(client):
    """Months paid outside the app (no TDS withheld) are imported; the next computed month catches up."""
    h, cid = ad_company(client)
    eid = add_employee(client, h, cid, "E001", basic="200000", ssf=True)
    for period, paid in ((1, "2026-07-31"), (2, "2026-08-31")):
        r = run(client, h, cid, "2083-84", period, paid)
        gross = "96774.19" if period == 1 else "200000"
        imp = client.put(f"/api/companies/{cid}/payroll-runs/{r['id']}/import", headers=h, json={
            "gross_includes_employer_ssf": True,
            "rows": [{"employee_id": eid, "gross": str(Decimal(gross) * Decimal("1.2")), "ssf_total": str(Decimal(gross) * Decimal("0.31")),
                      "cit": "0", "tds": "0"}]})
        assert imp.status_code == 200, imp.text
        assert imp.json()["source"] == "imported"
        # gross was given as cost-to-company: the employer's 20% is taken out again
        assert Decimal(imp.json()["payslips"][0]["gross"]) == Decimal(gross).quantize(Decimal("0.01"))
        finalize(client, h, cid, r["id"])
    r3 = finalize(client, h, cid, run(client, h, cid, "2083-84", 3, "2026-09-30")["id"])
    assert Decimal(r3["payslips"][0]["tds"]) > 0  # catches up on tax not withheld in the imported months
    st = client.get(f"/api/companies/{cid}/employees/{eid}/annual/2083-84", headers=h).json()
    assert [m["source"] for m in st["months"][:3]] == ["imported", "imported", "computed"]


def test_cit_fill_cap_and_previous_employer(client):
    h, cid = signup(client)
    e = client.post(f"/api/companies/{cid}/employees", headers=h, json={"code": "E1", "name": "N", "joined_on": "2025-01-01"}).json()
    client.put(f"/api/companies/{cid}/employees/{e['id']}/tax-profiles/2083-84", headers=h,
               json={"ssf_enrolled": True, "prior_income": "300000", "prior_retirement": "20000", "prior_tds": "5000"}).raise_for_status()
    client.post(f"/api/companies/{cid}/employees/{e['id']}/salary-structures", headers=h, json={
        "effective_from": "2025-01-01", "cit_mode": "fill_cap",
        "components": [{"kind": "basic", "amount": "100000"}, {"kind": "allowance", "amount": "150000"}]}).raise_for_status()
    r = client.post(f"/api/companies/{cid}/payroll-runs", headers=h, json={"payment_date": "2026-08-15"}).json()
    slip = client.post(f"/api/companies/{cid}/payroll-runs/{r['id']}/compute", headers=h).json()["payslips"][0]
    # SSF 31% of 12L = 3,72,000 + previous employer 20,000 → CIT fills the rest of 5L = 1,08,000 over 12 months
    assert Decimal(slip["cit"]) == Decimal("9000.00")
    assert Decimal(slip["projected_tax_without_cit"]) > Decimal(slip["projected_annual_tax"])
    detail = client.get(f"/api/companies/{cid}/payroll-runs/{r['id']}/payslips/{slip['id']}", headers=h).json()
    assert detail["inputs"]["prior_employment"]["tds"] == "5000.00"
    assert any("fills the retirement limit" in s["label"] for s in detail["trace"])


def test_ird_tds_csv(client):
    h, cid = signup(client)
    add_employee(client, h, cid, "E001", basic="150000")
    r = client.post(f"/api/companies/{cid}/payroll-runs", headers=h, json={"payment_date": "2026-08-15"}).json()
    finalize(client, h, cid, r["id"])
    lines = client.get(f"/api/companies/{cid}/reports/tds/2083-84.csv", headers=h).text.splitlines()
    assert lines[0].startswith("s.n.,PAN,Name,Shrawan 2083") and lines[0].endswith("TOTAL")
    assert lines[1].split(",")[2] == "Emp E001" and lines[-1].split(",")[2] == "Total"


def test_tds_start_policy_and_payslip_details(client):
    h, cid = signup(client)
    eid = add_employee(client, h, cid, "E001", basic="200000")
    client.put(f"/api/companies/{cid}/employees/{eid}", headers=h, json={
        "code": "E001", "name": "Emp E001", "joined_on": "2025-01-01", "department": "Web Development",
        "designation": "Developer", "cit_number": "CIT-1", "ssf_number": "SSF-1", "bank_account": "ACC-1"}).raise_for_status()
    # Only an HR admin may set it; withholding starts in Ashwin (period 3)
    assert client.put(f"/api/companies/{cid}/tds-policy/2083-84", headers=h, json={"start_period": 3}).json()["start_label"] == "Ashwin 2083"
    tds = []
    for paid in ("2026-08-15", "2026-09-16", "2026-10-17"):
        r = client.post(f"/api/companies/{cid}/payroll-runs", headers=h, json={"payment_date": paid}).json()
        tds.append(Decimal(finalize(client, h, cid, r["id"])["payslips"][0]["tds"]))
        last_run, slip_id = r["id"], None
    assert tds[0] == tds[1] == 0 and tds[2] > 0
    run = client.get(f"/api/companies/{cid}/payroll-runs/{last_run}", headers=h).json()
    slip = client.get(f"/api/companies/{cid}/payroll-runs/{last_run}/payslips/{run['payslips'][0]['id']}", headers=h).json()
    assert slip["employee"]["department"] == "Web Development" and slip["employee"]["bank_account"] == "ACC-1"
    assert slip["month_label"] == "Ashwin 2083" and slip["tds_starts"] == "Ashwin 2083"
    # Month 1's payslip explains why nothing was withheld
    run1 = client.get(f"/api/companies/{cid}/payroll-runs", headers=h).json()[-1]
    s1 = client.get(f"/api/companies/{cid}/payroll-runs/{run1['id']}", headers=h).json()["payslips"][0]
    d1 = client.get(f"/api/companies/{cid}/payroll-runs/{run1['id']}/payslips/{s1['id']}", headers=h).json()
    assert d1["inputs"]["tds_withheld"] is False and "Ashwin 2083" in d1["inputs"]["tds_note"]
    st = client.get(f"/api/companies/{cid}/employees/{eid}/annual/2083-84", headers=h).json()
    assert st["tds_start_label"] == "Ashwin 2083"
