"""Exact money arithmetic. Floats never enter the engine."""

from decimal import ROUND_HALF_UP, Decimal, getcontext
from fractions import Fraction

getcontext().prec = 34

ZERO = Decimal("0")
PAISA = Decimal("0.01")


def D(value) -> Decimal:
    if isinstance(value, float):
        raise TypeError("float passed to money arithmetic; use str or Decimal")
    if isinstance(value, Fraction):
        return Decimal(value.numerator) / Decimal(value.denominator)
    return Decimal(str(value)) if not isinstance(value, Decimal) else value


def fraction(value: str) -> Fraction:
    """Parse "1/3" or "0.05" into an exact Fraction."""
    return Fraction(str(value))


def apply_fraction(amount: Decimal, frac: Fraction) -> Decimal:
    """amount * frac, rounded to paisa (avoids 1/3 drift)."""
    return round_money(amount * frac.numerator / frac.denominator)


def round_money(amount: Decimal, places: int = 2) -> Decimal:
    return amount.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def fmt(amount: Decimal) -> str:
    """Nepali grouping (lakh/crore), as accountants write it: 12,34,567.89."""
    sign = "-" if amount < 0 else ""
    whole, frac = f"{abs(amount):.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return sign + ",".join(groups + [tail]) + "." + frac
