"""Nepali fiscal year (Shrawan 1 – Ashadh end) helpers."""

from __future__ import annotations

from datetime import date, timedelta

import nepali_datetime

MONTHS = ["Shrawan", "Bhadra", "Ashwin", "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra", "Baisakh", "Jestha", "Ashadh"]


def fy_start_year(d: date) -> int:
    bs = nepali_datetime.date.from_datetime_date(d)
    return bs.year if bs.month >= 4 else bs.year - 1


def fiscal_year_of(d: date) -> str:
    y = fy_start_year(d)
    return f"{y}/{(y + 1) % 100:02d}"


def fy_month(d: date) -> int:
    """1 = Shrawan … 12 = Ashadh."""
    return (nepali_datetime.date.from_datetime_date(d).month - 4) % 12 + 1


def fy_bounds(fiscal_year: str) -> tuple[date, date]:
    y = int(fiscal_year.split("/")[0])
    start = nepali_datetime.date(y, 4, 1).to_datetime_date()
    end = nepali_datetime.date(y + 1, 4, 1).to_datetime_date() - timedelta(days=1)
    return start, end


def service_months(fiscal_year: str, joined_on: date, left_on: date | None) -> tuple[int, int] | None:
    """(first_month, last_month) of service within the FY, or None if not employed in it."""
    start, end = fy_bounds(fiscal_year)
    if joined_on > end or (left_on and left_on < start):
        return None
    first = fy_month(joined_on) if joined_on >= start else 1
    last = fy_month(left_on) if left_on and left_on <= end else 12
    return first, last


def month_label(fiscal_year: str, month: int) -> str:
    y = int(fiscal_year.split("/")[0])
    return f"{MONTHS[month - 1]} {y if month <= 9 else y + 1}"
