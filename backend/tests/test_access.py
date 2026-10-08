"""Employee logins see only their own finalized pay; HR sees everyone. SSF/CIT month and year totals."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import update

from app.db import SessionLocal
from app.models import Invite

from .test_api import BHADRA_15, SHRAWAN_15, add_employee, client, clean, schema, signup  # noqa: F401  (fixtures)


def invite(client, h, cid, email, role="employee", employee_id=None):
    r = client.post(f"/api/companies/{cid}/invites", headers=h, json={"email": email, "role": role, "employee_id": employee_id})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def accept(client, token, password="employee-pass", name="Staff Member"):
    r = client.post(f"/api/auth/invites/{token}/accept", json={"name": name, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def two_months(client, h, cid):
    """E001 (SSF + CIT) and E002; Shrawan finalized, Bhadra still a draft."""
    a = add_employee(client, h, cid, "E001", basic="100000", ssf=True, cit="5000")
    b = add_employee(client, h, cid, "E002", basic="80000")
    r1 = client.post(f"/api/companies/{cid}/payroll-runs", headers=h, json={"payment_date": str(SHRAWAN_15)}).json()
    assert client.post(f"/api/companies/{cid}/payroll-runs/{r1['id']}/finalize", headers=h,
                       json={"acknowledge_unverified": True}).status_code == 200
    r2 = client.post(f"/api/companies/{cid}/payroll-runs", headers=h, json={"payment_date": str(BHADRA_15)}).json()
    assert client.post(f"/api/companies/{cid}/payroll-runs/{r2['id']}/compute", headers=h).status_code == 200
    return a, b, r1["id"], r2["id"]


def slip_id(client, h, cid, run_id, code):
    run = client.get(f"/api/companies/{cid}/payroll-runs/{run_id}", headers=h).json()
    return next(p["id"] for p in run["payslips"] if p["employee_code"] == code)


def test_employee_sees_only_own_finalized_pay(client):
    h, cid = signup(client)
    a, b, run1, run2 = two_months(client, h, cid)
    he = accept(client, invite(client, h, cid, "e001@example.com", employee_id=a))

    me = client.get("/api/auth/me", headers=he).json()["memberships"][0]
    assert me["role"] == "employee" and me["employee_id"] == a
    assert client.get(f"/api/companies/{cid}/me", headers=he).json()["code"] == "E001"

    # Every HR endpoint is closed to an employee login.
    for path in ("employees", f"employees/{a}", f"employees/{b}", "payroll-runs", f"payroll-runs/{run1}",
                 f"payroll-runs/{run1}/tds.csv", "reports/contributions/2083-84", f"employees/{a}/annual/2083-84",
                 "members", "audit", "invites"):
        assert client.get(f"/api/companies/{cid}/{path}", headers=he).status_code in (403,), path
    assert client.post(f"/api/companies/{cid}/payroll-runs/{run2}/compute", headers=he).status_code == 403

    # Year statement: finalized Shrawan only, not the Bhadra draft.
    st = client.get(f"/api/companies/{cid}/me/annual/2083-84", headers=he).json()
    paid = [m for m in st["months"] if m.get("payslip_id")]
    assert [m["month"] for m in paid] == [1] and st["months_paid"] == 1
    assert Decimal(st["totals"]["ssf_employee"]) == Decimal("11000.00")
    assert Decimal(st["totals"]["ssf_employer"]) == Decimal("20000.00")
    assert Decimal(st["totals"]["cit"]) == Decimal("5000.00")

    own = slip_id(client, h, cid, run1, "E001")
    assert client.get(f"/api/companies/{cid}/me/payslips/{own}", headers=he).json()["employee_code"] == "E001"
    # Someone else's payslip, or a draft: indistinguishable from "not found".
    assert client.get(f"/api/companies/{cid}/me/payslips/{slip_id(client, h, cid, run1, 'E002')}", headers=he).status_code == 404
    assert client.get(f"/api/companies/{cid}/me/payslips/{slip_id(client, h, cid, run2, 'E001')}", headers=he).status_code == 404


def test_hr_year_statement_and_contributions(client):
    h, cid = signup(client)
    a, b, run1, run2 = two_months(client, h, cid)

    raw = client.get(f"/api/companies/{cid}/employees/{a}/annual/2083-84", headers=h)
    assert '"cit":"10000.00"' in raw.text.replace(" ", "")  # exact decimal strings, never floats
    st = raw.json()
    assert [m["status"] for m in st["months"][:3]] == ["finalized", "draft", None]
    assert Decimal(st["totals"]["ssf_total"]) == Decimal("62000.00")  # 2 × (11,000 + 20,000)
    assert Decimal(st["totals"]["cit"]) == Decimal("10000.00")
    assert Decimal(st["tds_remaining"]) == Decimal(st["projected_annual_tax"]) - Decimal(st["totals"]["tds"])

    rep = client.get(f"/api/companies/{cid}/reports/contributions/2083-84", headers=h).json()  # finalized only
    assert Decimal(rep["totals"]["ssf_total"]) == Decimal("31000.00") and Decimal(rep["totals"]["cit"]) == Decimal("5000.00")
    assert [e["code"] for e in rep["employees"]] == ["E001", "E002"]
    assert Decimal(rep["months"][0]["ssf_employer"]) == Decimal("20000.00") and rep["months"][1]["status"] is None

    rep2 = client.get(f"/api/companies/{cid}/reports/contributions/2083-84", headers=h, params={"include_drafts": True}).json()
    assert Decimal(rep2["totals"]["ssf_total"]) == Decimal("62000.00")

    lines = client.get(f"/api/companies/{cid}/reports/contributions/2083-84.csv", headers=h).text.splitlines()
    assert lines[0].startswith("employee_code") and any(",year,Year total," in l for l in lines)


def test_invite_rules(client):
    h, cid = signup(client)
    a = add_employee(client, h, cid, "E001")
    bad = client.post(f"/api/companies/{cid}/invites", headers=h, json={"email": "x@example.com", "role": "employee"})
    assert bad.status_code == 422  # employee login must be tied to a record

    token = invite(client, h, cid, "e001@example.com", employee_id=a)
    info = client.get(f"/api/auth/invites/{token}").json()
    assert info["employee_name"] == "Emp E001" and info["has_account"] is False
    accept(client, token)
    assert client.post(f"/api/auth/invites/{token}/accept", json={"name": "x", "password": "whatever-1"}).status_code == 404
    dup = client.post(f"/api/companies/{cid}/invites", headers=h, json={"email": "z@example.com", "role": "employee", "employee_id": a})
    assert dup.status_code == 409  # one login per employee

    # Expired link.
    t2 = invite(client, h, cid, "hr2@example.com", role="accountant")
    with SessionLocal() as db:
        db.execute(update(Invite).where(Invite.email == "hr2@example.com").values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
        db.commit()
    assert client.post(f"/api/auth/invites/{t2}/accept", json={"name": "HR", "password": "hr-pass-123"}).status_code == 410

    # Someone who already has an account must prove it with their own password.
    signup(client, "boss@example.com", "Other Co")
    t3 = invite(client, h, cid, "boss@example.com", role="viewer")
    assert client.get(f"/api/auth/invites/{t3}").json()["has_account"] is True
    assert client.post(f"/api/auth/invites/{t3}/accept", json={"password": "not-their-pass"}).status_code == 401
    hb = accept(client, t3, password="s3cret-pass")
    roles = {m["company_id"]: m["role"] for m in client.get("/api/auth/me", headers=hb).json()["memberships"]}
    assert roles[cid] == "viewer"
    assert client.get(f"/api/companies/{cid}/employees", headers=hb).status_code == 200  # auditor sees all salaries


def test_hr_staff_cannot_invite_and_access_can_be_removed(client):
    h, cid = signup(client)
    a = add_employee(client, h, cid, "E001")
    hr = accept(client, invite(client, h, cid, "payroll@example.com", role="accountant"))
    assert client.post(f"/api/companies/{cid}/invites", headers=hr,
                       json={"email": "q@example.com", "role": "employee", "employee_id": a}).status_code == 403
    he = accept(client, invite(client, h, cid, "e001@example.com", employee_id=a))
    members = client.get(f"/api/companies/{cid}/members", headers=h).json()
    emp_user = next(m for m in members if m["role"] == "employee")
    assert emp_user["employee_name"] == "Emp E001"
    assert client.delete(f"/api/companies/{cid}/members/{emp_user['user_id']}", headers=h).status_code == 204
    assert client.get(f"/api/companies/{cid}/me", headers=he).status_code == 404
    owner = next(m for m in members if m["role"] == "admin")
    assert client.delete(f"/api/companies/{cid}/members/{owner['user_id']}", headers=h).status_code == 409
