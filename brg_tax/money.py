"""Money arithmetic in integer pence.

Every amount in the engine is an ``int`` of pence and every rate is an ``int`` of basis points
(1% = 100 bp), so the Python engine and ``dashboard/engine_mirror.js`` produce identical results.
Rounding is half-up (away from zero) to the penny, applied at the points documented in each
computation.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Union

Number = Union[int, float, str, Decimal]


def to_pence(value: Any) -> int:
    """Parse a money amount (``"£1,234.56"``, ``"(12.00)"``, ``1234.5``) into pence."""
    if value is None:
        return 0
    if isinstance(value, bool):
        raise ValueError("boolean is not an amount")
    if isinstance(value, int):
        return value * 100
    text = str(value).strip()
    if not text:
        return 0
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace("£", "").replace(",", "").replace(" ", "")
    if text.startswith("-"):
        negative = not negative
        text = text[1:]
    try:
        pence = int((Decimal(text) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except InvalidOperation as exc:
        raise ValueError(f"not an amount: {value!r}") from exc
    return -pence if negative else pence


def pounds(p: int) -> float:
    return p / 100


def bp(rate_percent: Number) -> int:
    """A percentage (e.g. ``33.75``) as basis points (``3375``)."""
    return int((Decimal(str(rate_percent)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def muldiv(amount: int, num: int, den: int) -> int:
    """``amount * num / den`` rounded half-up (away from zero) to an integer."""
    if den <= 0:
        raise ValueError("denominator must be positive")
    n = amount * num
    sign = -1 if n < 0 else 1
    return sign * ((2 * abs(n) + den) // (2 * den))


def at_rate(amount: int, rate_bp: int) -> int:
    """Tax at ``rate_bp`` on ``amount`` pence, to the nearest penny."""
    return muldiv(amount, rate_bp, 10000)


def clamp(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, x))


def fmt(p: int, sign: bool = False) -> str:
    neg = p < 0
    s = f"£{abs(p) // 100:,}.{abs(p) % 100:02d}"
    if neg:
        return f"({s})"
    return ("+" + s) if sign and p > 0 else s
