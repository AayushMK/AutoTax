"""Build the demo company with dummy payroll: all of FY 2082/83, plus FY 2083/84 so far.

    cd backend && uv run python scripts/seed_demo.py --reset   # wipe the LOCAL dev database first
    cd backend && uv run python scripts/seed_demo.py           # into an empty database

Everything goes through the real API in-process (same validation, tax engine and audit log as the
app). Foreign-currency pay uses the real NRB rates for each payment date, fetched live.
All people, PANs and emails are fictitious.

Logins created:  HR admin  demo@example.com / demo-pass-1
                 Employee  bikash@example.com / bikash-pass-1   (Bikash Thapa, E-001)
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

import nepali_datetime as nd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402

HR = {"email": "demo@example.com", "password": "demo-pass-1", "name": "Sunita Shrestha"}
EMPLOYEE_LOGIN = ("E-001", "bikash@example.com", "bikash-pass-1")
COMPANY = {"company_name": "Himal Software Pvt. Ltd.", "company_pan": "609876543"}


def bs(y: int, m: int, d: int) -> date:
    return nd.date(y, m, d).to_datetime_date()


def month_end(y: int, m: int) -> date:
    ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
    return bs(ny, nm, 1) - timedelta(days=1)


def fy_months(start_bs_year: int) -> list[date]:
    """Payment dates (last day of each BS month) for the FY starting Shrawan of `start_bs_year`."""
    return [month_end(start_bs_year, m) for m in range(4, 13)] + [month_end(start_bs_year + 1, m) for m in range(1, 4)]


def comp(kind, amount, currency="NPR", note=""):
    return {"kind": kind, "amount": amount, "currency": currency, "description": note}


# code, name, pan, joined, left, tax profile (same both years), [(effective_from, components, cit)]
EMPLOYEES = [
    ("E-001", "Bikash Thapa", "301234567", date(2024, 4, 1), None,
     {"ssf_enrolled": True, "life_insurance_premium": "45000"},
     [(date(2024, 4, 1), [comp("basic", "1500", "USD"), comp("allowance", "300", "USD")], "5000"),
      (date(2026, 10, 1), [comp("basic", "815", "USD"), comp("allowance", "544", "USD"), comp("allowance", "267", "USD")], "0")]),
    ("E-002", "Anjali Gurung", "302345678", date(2025, 2, 15), None,
     {"gender": "female", "health_insurance_premium": "18000"},
     [(date(2025, 2, 15), [comp("basic", "120000"), comp("allowance", "15000", note="communication")], "0")]),
    ("E-003", "Ramesh Karki", "303456789", date(2023, 7, 20), None,
     {"ssf_enrolled": True, "filing": "couple", "remote_area": "C"},
     [(date(2023, 7, 20), [comp("basic", "65000")], "0")]),
    ("E-004", "Pratiksha Adhikari", "304567890", date(2022, 5, 1), None,
     {"gender": "female", "ssf_enrolled": True, "life_insurance_premium": "25000"},
     [(date(2022, 5, 1), [comp("basic", "85000"), comp("allowance", "10000", note="transport")], "3000")]),
    ("E-005", "Suman Rai", "305678901", date(2023, 1, 9), None,
     {"health_insurance_premium": "20000"},
     [(date(2023, 1, 9), [comp("basic", "2200", "USD"), comp("allowance", "200", "USD", "remote work")], "10000")]),
    ("E-006", "Nirajan Shah", "306789012", date(2021, 8, 16), None,
     {"filing": "couple", "ssf_enrolled": True, "life_insurance_premium": "40000", "health_insurance_premium": "15000"},
     [(date(2021, 8, 16), [comp("basic", "150000"), comp("allowance", "20000", note="management")], "8000")]),
    ("E-007", "Kabita Tamang", "307890123", bs(2082, 7, 1), None,  # joined Kartik 2082
     {"gender": "female", "ssf_enrolled": True},
     [(bs(2082, 7, 1), [comp("basic", "60000")], "0")]),
    ("E-008", "Dipesh Joshi", "308901234", date(2020, 3, 2), month_end(2082, 9),  # left end of Poush 2082
     {},
     [(date(2020, 3, 2), [comp("basic", "70000"), comp("allowance", "5000")], "0")]),
    ("E-009", "Asmita Bhandari", "309012345", date(2024, 2, 1), None,
     {"gender": "female", "ssf_enrolled": True},
     [(date(2024, 2, 1), [comp("basic", "1200", "USD")], "2000"),
      (bs(2082, 10, 1), [comp("basic", "1400", "USD", "raise from Magh 2082")], "2000")]),
    ("E-010", "Rohan Maharjan", "310123456", date(2023, 11, 20), None,
     {"disabled": True, "remote_area": "D"},
     [(date(2023, 11, 20), [comp("basic", "45000")], "0")]),
    ("E-011", "Sarah Lindqvist", None, date(2025, 6, 1), None,  # foreign consultant, non-resident
     {"resident": False, "gender": "female"},
     [(date(2025, 6, 1), [comp("basic", "3000", "USD", "consulting retainer")], "0")]),
    ("E-012", "Bishal Gurung", "312345678", date(2019, 4, 15), None,
     {"ssf_enrolled": True, "life_insurance_premium": "60000", "donation": "50000"},
     [(date(2019, 4, 15), [comp("basic", "110000"), comp("allowance", "12000")], "15000")]),
]

CHAITRA_BONUS = {"E-001": comp("bonus", "500", "USD", "annual performance bonus"),
                 "E-006": comp("bonus", "80000", note="annual performance bonus"),
                 "E-012": comp("bonus", "60000", note="annual performance bonus")}


def reset_local_db() -> None:
    host = urlparse(settings.database_url.replace("+psycopg", "")).hostname
    if host not in ("localhost", "127.0.0.1", "::1", "db"):
        sys.exit(f"--reset refused: {host} is not a local development database")
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    print("Local database reset.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="wipe the local dev database first")
    args = ap.parse_args()
    if not settings.fetch_fx_automatically:
        sys.exit("FETCH_FX=0: the demo needs live NRB rates for USD salaries")
    if args.reset:
        reset_local_db()

    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    r = c.post("/api/auth/signup", json={**HR, **COMPANY})
    if r.status_code == 409:
        sys.exit("The demo account already exists. Run with --reset to rebuild it.")
    r.raise_for_status()
    c.headers["Authorization"] = f"Bearer {r.json()['token']}"
    cid = c.get("/api/auth/me").json()["memberships"][0]["company_id"]
    api = f"/api/companies/{cid}"

    ids: dict[str, int] = {}
    for code, name, pan, joined, left, profile, structures in EMPLOYEES:
        e = c.post(f"{api}/employees", json={
            "code": code, "name": name, "pan": pan, "joined_on": str(joined), "left_on": str(left) if left else None,
            "email": f"{name.split()[0].lower()}@example.com"})
        e.raise_for_status()
        ids[code] = eid = e.json()["id"]
        for fy in ("2082-83", "2083-84"):
            c.put(f"{api}/employees/{eid}/tax-profiles/{fy}", json=profile).raise_for_status()
        for eff, comps, cit in structures:
            c.post(f"{api}/employees/{eid}/salary-structures",
                   json={"effective_from": str(eff), "components": comps, "cit_monthly": cit}).raise_for_status()
    print(f"{len(ids)} employees added.")

    def basic_on(code: str, on: date) -> dict | None:
        """The employee's basic-salary component on `on`, or None if not in service."""
        _, _, _, joined, left, _, structures = next(e for e in EMPLOYEES if e[0] == code)
        if joined > on or (left and left < on):
            return None
        eff, comps, _ = max((s for s in structures if s[0] <= on), key=lambda s: s[0])
        return next(x for x in comps if x["kind"] == "basic")

    def run_month(pay_date: date, adjustments: list[tuple[str, dict]], finalize: bool) -> None:
        run = c.post(f"{api}/payroll-runs", json={"payment_date": str(pay_date)})
        run.raise_for_status()
        rid = run.json()["id"]
        for code, adj in adjustments:
            c.post(f"{api}/payroll-runs/{rid}/adjustments", json={"employee_id": ids[code], **adj}).raise_for_status()
        if finalize:
            res = c.post(f"{api}/payroll-runs/{rid}/finalize", json={"acknowledge_unverified": True})
        else:
            res = c.post(f"{api}/payroll-runs/{rid}/compute")
        if res.status_code != 200:
            sys.exit(f"{pay_date}: {res.status_code} {res.text}")
        d = res.json()
        t = d["totals"]
        print(f"  {d['month_label']:<14} {d['status']:<9} {len(d['payslips']):>2} payslips  gross {t['gross']:>13}  "
              f"TDS {t['tds']:>11}  SSF {t['ssf_employee']} + {t['ssf_employer']}  CIT {t['cit']}")

    print("FY 2082/83")
    for month, pay_date in enumerate(fy_months(2082), start=1):
        adj: list[tuple[str, dict]] = []
        if month == 3:  # Ashwin: Dashain allowance, one month's basic for everyone in service
            for code in ids:
                b = basic_on(code, pay_date)
                if b:
                    adj.append((code, comp("dashain", b["amount"], b["currency"], "Dashain 2082, one month's basic")))
        if month == 9:  # Chaitra: performance bonuses
            adj += list(CHAITRA_BONUS.items())
        run_month(pay_date, adj, finalize=True)

    print("FY 2083/84")
    shrawan, bhadra = fy_months(2083)[:2]
    run_month(shrawan, [], finalize=True)
    run_month(bhadra, [("E-002", comp("dashain", "135000", note="one month basic + allowance"))], finalize=False)

    # Employee self-service login for Bikash.
    code, email, password = EMPLOYEE_LOGIN
    inv = c.post(f"{api}/invites", json={"email": email, "role": "employee", "employee_id": ids[code]})
    inv.raise_for_status()
    c.post(f"/api/auth/invites/{inv.json()['token']}/accept",
           json={"name": "Bikash Thapa", "password": password}).raise_for_status()

    rep = c.get(f"{api}/reports/contributions/2082-83").json()["totals"]
    print(f"FY 2082/83 SSF {rep['ssf_total']} (11% {rep['ssf_employee']}, 20% {rep['ssf_employer']}), CIT {rep['cit']}")
    print(f"Logins: {HR['email']} / {HR['password']} (HR admin), {email} / {password} (employee)")


if __name__ == "__main__":
    main()
