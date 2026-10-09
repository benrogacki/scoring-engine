"""Tax-year and financial-year arithmetic."""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import List, Tuple


def tax_year_of(d: date) -> str:
    """Income tax year label (6 April to 5 April), e.g. ``2025-26``."""
    start = d.year if (d.month, d.day) >= (4, 6) else d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def tax_year_bounds(label: str) -> Tuple[date, date]:
    y = int(label[:4])
    return date(y, 4, 6), date(y + 1, 4, 5)


def fy_of(d: date) -> int:
    """Corporation tax financial year (FY2025 = 1 April 2025 to 31 March 2026)."""
    return d.year if d.month >= 4 else d.year - 1


def fy_bounds(fy: int) -> Tuple[date, date]:
    return date(fy, 4, 1), date(fy + 1, 3, 31)


def fy_label_to_params_label(fy: int) -> str:
    return f"{fy}-{str(fy + 1)[2:]}"


def is_month_end(d: date) -> bool:
    return d.day == calendar.monthrange(d.year, d.month)[1]


def add_months(d: date, months: int, month_end_rule: bool = True) -> date:
    """Add calendar months. With ``month_end_rule`` a month-end date maps to a month-end date
    (30 June + 9 months = 31 March), the convention HMRC and Companies House use for deadlines."""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    last = calendar.monthrange(y, m)[1]
    if month_end_rule and is_month_end(d):
        return date(y, m, last)
    return date(y, m, min(d.day, last))


def days_incl(start: date, end: date) -> int:
    return (end - start).days + 1


def overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> int:
    s, e = max(a_start, b_start), min(a_end, b_end)
    return days_incl(s, e) if e >= s else 0


def fy_slices(start: date, end: date) -> List[Tuple[int, date, date, int]]:
    """Split a period into financial-year slices: (fy, slice_start, slice_end, days)."""
    out = []
    cur = start
    while cur <= end:
        fy = fy_of(cur)
        _, fy_end = fy_bounds(fy)
        e = min(end, fy_end)
        out.append((fy, cur, e, days_incl(cur, e)))
        cur = e + timedelta(days=1)
    return out


def tax_years_spanned(start: date, end: date) -> List[str]:
    out, cur = [], start
    while cur <= end:
        label = tax_year_of(cur)
        out.append(label)
        cur = tax_year_bounds(label)[1] + timedelta(days=1)
    return out


def twelve_months_from(start: date) -> date:
    """The last day of the 12 months beginning on ``start``."""
    return add_months(start, 12, month_end_rule=False) - timedelta(days=1)
