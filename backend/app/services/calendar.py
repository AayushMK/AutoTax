"""Fiscal year (Shrawan 1 – Ashadh end) and pay periods for the two payroll calendars.

    "bs"  Nepali months: 12 periods, Shrawan … Ashadh.
    "ad"  English months: 13 periods. July is split between fiscal years: the year opens with
          the part of July from Shrawan 1 (e.g. 17–31 July) and closes with 1 July – Ashadh end.

A period's share for an employee is (days employed in the period) / (days in that calendar month):
1 for a full month, 15/31 for 17–31 July, 15/31 for someone joining on the 17th of a 31-day month.
"""

from __future__ import annotations

import calendar as _cal
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from typing import Literal

import nepali_datetime

Calendar = Literal["bs", "ad"]
MONTHS = ["Shrawan", "Bhadra", "Ashwin", "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra", "Baisakh", "Jestha", "Ashadh"]


def fy_start_year(d: date) -> int:
    bs = nepali_datetime.date.from_datetime_date(d)
    return bs.year if bs.month >= 4 else bs.year - 1


def fiscal_year_of(d: date) -> str:
    y = fy_start_year(d)
    return f"{y}/{(y + 1) % 100:02d}"


def fy_month(d: date) -> int:
    """Nepali-month period of a date: 1 = Shrawan … 12 = Ashadh."""
    return (nepali_datetime.date.from_datetime_date(d).month - 4) % 12 + 1


def fy_bounds(fiscal_year: str) -> tuple[date, date]:
    y = int(fiscal_year.split("/")[0])
    start = nepali_datetime.date(y, 4, 1).to_datetime_date()
    end = nepali_datetime.date(y + 1, 4, 1).to_datetime_date() - timedelta(days=1)
    return start, end


@dataclass(frozen=True)
class Period:
    fiscal_year: str
    index: int
    start: date
    end: date
    label: str
    month_days: int  # days in the calendar month the period belongs to (proration denominator)

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def periods(fiscal_year: str, cal: Calendar = "bs") -> list[Period]:
    start, end = fy_bounds(fiscal_year)
    if cal == "bs":
        y = int(fiscal_year.split("/")[0])
        out = []
        for i in range(12):
            by, bm = (y, 4 + i) if i < 9 else (y + 1, i - 8)
            s = nepali_datetime.date(by, bm, 1).to_datetime_date()
            ny, nm = (by, bm + 1) if bm < 12 else (by + 1, 1)
            e = nepali_datetime.date(ny, nm, 1).to_datetime_date() - timedelta(days=1)
            out.append(Period(fiscal_year, i + 1, s, e, f"{MONTHS[i]} {by}", (e - s).days + 1))
        return out
    # English months: July (part) … June, July (part).
    out = []
    july_days = 31
    out.append(Period(fiscal_year, 1, start, date(start.year, 7, 31),
                      f"July {start.year} ({start.day}–31)", july_days))
    y, m = start.year, 8
    for i in range(2, 13):
        last = _cal.monthrange(y, m)[1]
        out.append(Period(fiscal_year, i, date(y, m, 1), date(y, m, last), f"{_cal.month_name[m]} {y}", last))
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    out.append(Period(fiscal_year, 13, date(end.year, 7, 1), end, f"July {end.year} (1–{end.day})", july_days))
    return out


def period(fiscal_year: str, index: int, cal: Calendar = "bs") -> Period:
    ps = periods(fiscal_year, cal)
    if not 1 <= index <= len(ps):
        raise ValueError(f"period {index} does not exist in FY {fiscal_year} ({len(ps)} periods)")
    return ps[index - 1]


def period_of(d: date, cal: Calendar = "bs") -> Period:
    fy = fiscal_year_of(d)
    return next(p for p in periods(fy, cal) if p.start <= d <= p.end)


def share(p: Period, joined_on: date, left_on: date | None) -> Fraction:
    """Part of a full month this employee is paid for in period `p` (0 if not employed in it)."""
    s = max(p.start, joined_on)
    e = min(p.end, left_on) if left_on else p.end
    days = (e - s).days + 1
    return Fraction(max(days, 0), p.month_days)


def service_periods(fiscal_year: str, joined_on: date, left_on: date | None, cal: Calendar = "bs") -> tuple[int, int] | None:
    """(first, last) period indexes this employee is paid in during the FY, or None."""
    idx = [p.index for p in periods(fiscal_year, cal) if share(p, joined_on, left_on) > 0]
    return (idx[0], idx[-1]) if idx else None


def service_months(fiscal_year: str, joined_on: date, left_on: date | None) -> tuple[int, int] | None:
    return service_periods(fiscal_year, joined_on, left_on, "bs")


def month_label(fiscal_year: str, month: int, cal: Calendar = "bs") -> str:
    return period(fiscal_year, month, cal).label
