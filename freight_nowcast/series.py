"""Time-series primitives: observations, monthly aggregation and momentum transforms.

Series are kept as plain sorted lists of ``(date, value)`` and monthly panels as
``{Month: value}`` dicts so everything stays standard-library only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

Month = Tuple[int, int]  # (year, month)
Monthly = Dict[Month, float]


def month_of(d: date) -> Month:
    return (d.year, d.month)


def add_months(m: Month, n: int) -> Month:
    idx = m[0] * 12 + (m[1] - 1) + n
    return (idx // 12, idx % 12 + 1)


def month_str(m: Month) -> str:
    return f"{m[0]:04d}-{m[1]:02d}"


def parse_month(text: str) -> Month:
    y, mo = text.strip()[:7].split("-")
    return (int(y), int(mo))


def month_range(start: Month, end: Month) -> List[Month]:
    out, m = [], start
    while m <= end:
        out.append(m)
        m = add_months(m, 1)
    return out


def days_in_month(m: Month) -> int:
    nxt = add_months(m, 1)
    return (date(nxt[0], nxt[1], 1) - date(m[0], m[1], 1)).days


@dataclass
class Series:
    """One published series as it arrived from its source (any frequency)."""

    id: str
    observations: List[Tuple[date, float]]
    frequency: str = "M"  # D (daily / working-daily), W, M
    source: str = ""
    meta: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        clean = {}
        for d, v in self.observations:
            if v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            clean[d] = float(v)  # last write wins on duplicate dates (revisions)
        self.observations = sorted(clean.items())

    @property
    def last_date(self) -> Optional[date]:
        return self.observations[-1][0] if self.observations else None

    def to_monthly(self, as_of: Optional[date] = None, min_coverage: float = 0.0) -> Tuple[Monthly, Dict[Month, float]]:
        """Average sub-monthly observations to calendar months.

        Returns ``(values, coverage)``. ``coverage`` is the share of the month's
        days spanned by observations (1.0 for monthly data); the latest month of
        a daily series is a *month-to-date* reading, which is the whole point of
        the daily toll index, and is reported with coverage < 1 so the report can
        flag it as provisional. Months below ``min_coverage`` are dropped.
        """
        obs = [(d, v) for d, v in self.observations if as_of is None or d <= as_of]
        if self.frequency == "M":
            vals = {month_of(d): v for d, v in obs}
            return vals, {m: 1.0 for m in vals}
        buckets: Dict[Month, List[Tuple[date, float]]] = {}
        for d, v in obs:
            buckets.setdefault(month_of(d), []).append((d, v))
        vals, cov = {}, {}
        last_month = month_of(obs[-1][0]) if obs else None
        for m, rows in buckets.items():
            if m == last_month:
                span = rows[-1][0].day / days_in_month(m)
            else:
                span = 1.0
            if span < min_coverage:
                continue
            vals[m] = sum(v for _, v in rows) / len(rows)
            cov[m] = round(span, 3)
        return vals, cov


def sorted_months(values: Monthly) -> List[Month]:
    return sorted(values)


def pct_change(values: Monthly, periods: int) -> Monthly:
    out = {}
    for m, v in values.items():
        prev = values.get(add_months(m, -periods))
        if prev not in (None, 0):
            out[m] = (v / prev - 1.0) * 100.0
    return out


def rolling_mean(values: Monthly, window: int) -> Monthly:
    out = {}
    for m in values:
        win = [values.get(add_months(m, -k)) for k in range(window)]
        if all(x is not None for x in win):
            out[m] = sum(win) / window
    return out


def transform(values: Monthly, how: str) -> Monthly:
    """Turn a level into momentum.

    - ``mom``   month-on-month % change
    - ``yoy``   year-on-year % change (robust to residual seasonality)
    - ``3m3m``  % change of the latest 3-month average on the prior 3 months,
                annualised: smooth enough to read, quick enough to turn
    - ``diff``  first difference (for series already in rates / balances)
    - ``level`` unchanged
    """
    if how == "mom":
        return pct_change(values, 1)
    if how == "yoy":
        return pct_change(values, 12)
    if how == "3m3m":
        avg = rolling_mean(values, 3)
        return {m: ((1 + g / 100.0) ** 4 - 1) * 100.0 for m, g in pct_change(avg, 3).items()}
    if how == "diff":
        return {m: v - values[add_months(m, -1)] for m, v in values.items() if add_months(m, -1) in values}
    if how == "level":
        return dict(values)
    raise ValueError(f"unknown transform {how!r} (use mom, yoy, 3m3m, diff or level)")


def mean_std(xs: Sequence[float]) -> Tuple[float, float]:
    n = len(xs)
    if n == 0:
        return float("nan"), float("nan")
    mu = sum(xs) / n
    if n < 2:
        return mu, float("nan")
    var = sum((x - mu) ** 2 for x in xs) / (n - 1)
    return mu, math.sqrt(var)


def rolling_zscore(values: Monthly, window: int = 60, min_periods: int = 24, clip: float = 4.0) -> Monthly:
    """Z-score each month against the trailing ``window`` months (inclusive).

    Only past data enters each standardisation, so a historical z is what a
    real-time reader would have seen (modulo data revisions): no look-ahead.
    """
    months = sorted(values)
    out = {}
    for i, m in enumerate(months):
        hist = [values[x] for x in months[max(0, i - window + 1): i + 1]]
        if len(hist) < min_periods:
            continue
        mu, sd = mean_std(hist)
        if not sd or math.isnan(sd):
            continue
        out[m] = max(-clip, min(clip, (values[m] - mu) / sd))
    return out


def iter_aligned(*series: Monthly) -> Iterable[Tuple[Month, Tuple[float, ...]]]:
    common = set(series[0])
    for s in series[1:]:
        common &= set(s)
    for m in sorted(common):
        yield m, tuple(s[m] for s in series)
