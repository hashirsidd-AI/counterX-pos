"""Safe money arithmetic for PKR. Everything is Decimal, 2 dp, HALF_UP."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from ..config import DEFAULT_CURRENCY_SYMBOL

TWOPLACES = Decimal("0.01")


def d(value) -> Decimal:
    """Coerce anything numeric-ish to Decimal without float error."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def q(value) -> Decimal:
    """Quantize to 2 decimal places (PKR paisa)."""
    return d(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def fmt(amount, symbol: str = DEFAULT_CURRENCY_SYMBOL) -> str:
    """Pakistani number format: Rs1,234.50"""
    a = q(amount)
    sign = "-" if a < 0 else ""
    a = abs(a)
    whole, _, frac = format(a, ".2f").partition(".")
    grouped = ""
    while len(whole) > 3:
        grouped = "," + whole[-3:] + grouped
        whole = whole[:-3]
    grouped = whole + grouped
    return f"{sign}{symbol}{grouped}.{frac}"
