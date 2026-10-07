"""Foreign-currency conversion using stored official (NRB) rates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from .models import IncomeLine
from .money import D, fmt, round_money
from .rules import RuleSet
from .trace import Trace

MAX_FALLBACK_DAYS = 7


class FxRateMissing(LookupError):
    pass


@dataclass(frozen=True)
class FxRate:
    currency: str
    on: date
    buy: Decimal
    sell: Decimal
    unit: int = 1  # NRB quotes e.g. INR per 100, JPY per 10
    source: str = "NRB"
    override_reason: str | None = None

    def per_unit(self, rate_type: str) -> Decimal:
        if rate_type == "buying":
            r = self.buy
        elif rate_type == "selling":
            r = self.sell
        elif rate_type == "mid":
            r = (self.buy + self.sell) / 2
        else:
            raise ValueError(f"unknown fx.rate_type {rate_type!r}")
        return r / self.unit


class FxTable:
    def __init__(self, rates: list[FxRate] = ()):
        self._rates: dict[tuple[str, date], FxRate] = {}
        for r in rates:
            self.add(r)

    def add(self, rate: FxRate) -> None:
        key = (rate.currency.upper(), rate.on)
        existing = self._rates.get(key)
        # A manual override always beats the published rate for the same day.
        if existing and existing.override_reason and not rate.override_reason:
            return
        self._rates[key] = rate

    def lookup(self, currency: str, on: date) -> FxRate:
        """Rate for `on`, or the most recent published rate within MAX_FALLBACK_DAYS."""
        for back in range(MAX_FALLBACK_DAYS + 1):
            r = self._rates.get((currency.upper(), on - timedelta(days=back)))
            if r:
                return r
        raise FxRateMissing(f"no {currency} rate on or within {MAX_FALLBACK_DAYS} days before {on}")


def to_npr(line: IncomeLine, fx: FxTable, rules: RuleSet, trace: Trace) -> Decimal:
    if line.currency.upper() == "NPR":
        return line.amount
    if line.payment_date is None:
        raise ValueError(f"{line.kind} line in {line.currency} needs a payment_date for FX conversion")
    rate_type = rules.value("fx.rate_type")
    rate = fx.lookup(line.currency, line.payment_date)
    per_unit = rate.per_unit(rate_type)
    npr = round_money(D(line.amount) * per_unit)
    note = f" (rate of {rate.on}, nearest prior to {line.payment_date})" if rate.on != line.payment_date else ""
    override = f" OVERRIDE: {rate.override_reason}" if rate.override_reason else ""
    trace.add(
        f"FX {line.kind} {line.currency} {fmt(line.amount)} → NPR",
        npr,
        f"{fmt(line.amount)} × {per_unit} ({rate.source} {rate_type}, {rate.on}){note}{override}",
        rules.cite("fx.rate_type"),
    )
    return npr
