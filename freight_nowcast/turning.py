"""Turning points: confirmed (Bry-Boschan style) and provisional (real-time) flags.

Confirmed peaks/troughs need ``window`` months either side, so they always lag.
The provisional rule is what a reader can act on at the ragged edge: the
composite has moved ``threshold`` z away from its recent extreme *and* kept
going for ``confirm_months`` months.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .series import Month, Monthly, add_months, month_str


@dataclass
class TurningPoint:
    month: Month
    kind: str          # peak | trough | cross_up | cross_down
    status: str        # confirmed | provisional | event
    value: float
    detected: Month    # first month at which the flag could be raised

    def as_row(self) -> Dict[str, object]:
        return {"month": month_str(self.month), "kind": self.kind, "status": self.status,
                "value": round(self.value, 3), "detected": month_str(self.detected)}


def confirmed_turning_points(x: Monthly, window: int = 5, min_phase: int = 5, min_cycle: int = 15,
                             min_amplitude: float = 0.5) -> List[TurningPoint]:
    months = sorted(x)
    cands: List[TurningPoint] = []
    for i in range(window, len(months) - window):
        m = months[i]
        span = [x[months[j]] for j in range(i - window, i + window + 1)]
        if x[m] == max(span) and span.count(x[m]) == 1:
            cands.append(TurningPoint(m, "peak", "confirmed", x[m], months[i + window]))
        elif x[m] == min(span) and span.count(x[m]) == 1:
            cands.append(TurningPoint(m, "trough", "confirmed", x[m], months[i + window]))

    def gap(a: Month, b: Month) -> int:
        return (b[0] - a[0]) * 12 + b[1] - a[1]

    changed = True
    while changed:  # enforce alternation, minimum phase/cycle and amplitude
        changed = False
        for i in range(len(cands) - 1):
            a, b = cands[i], cands[i + 1]
            if a.kind == b.kind:
                keep_a = (a.value >= b.value) if a.kind == "peak" else (a.value <= b.value)
                cands.pop(i + 1 if keep_a else i)
                changed = True
                break
            if gap(a.month, b.month) < min_phase or abs(a.value - b.value) < min_amplitude:
                # too short or too shallow to be a cycle phase: drop both; the
                # alternation rule then keeps the more extreme of the neighbours
                del cands[i:i + 2]
                changed = True
                break
        for i in range(len(cands) - 2):
            if not changed and gap(cands[i].month, cands[i + 2].month) < min_cycle:
                a, c = cands[i], cands[i + 2]
                keep_a = (a.value >= c.value) if a.kind == "peak" else (a.value <= c.value)
                cands.pop(i + 2 if keep_a else i)
                changed = True
                break
    return cands


def provisional_turn(x: Monthly, last_confirmed: Optional[TurningPoint], lookback: int = 12,
                     threshold: float = 0.5, confirm_months: int = 2) -> Optional[TurningPoint]:
    """Flag a turn at the ragged edge that ``confirmed_turning_points`` cannot see yet."""
    months = sorted(x)
    if len(months) < confirm_months + 2:
        return None
    end = months[-1]
    start = add_months(end, -lookback)
    if last_confirmed:
        start = max(start, add_months(last_confirmed.month, 1))
    recent = [m for m in months if m >= start]
    if len(recent) < confirm_months + 1:
        return None
    tail = [x[m] for m in months[-(confirm_months + 1):]]
    falling = all(b < a for a, b in zip(tail, tail[1:]))
    rising = all(b > a for a, b in zip(tail, tail[1:]))
    hi = max(recent, key=lambda m: x[m])
    lo = min(recent, key=lambda m: x[m])
    want = None
    if last_confirmed is not None:
        want = "trough" if last_confirmed.kind == "peak" else "peak"
    if falling and hi != end and x[hi] - x[end] >= threshold and want in (None, "peak"):
        return TurningPoint(hi, "peak", "provisional", x[hi], end)
    if rising and lo != end and x[end] - x[lo] >= threshold and want in (None, "trough"):
        return TurningPoint(lo, "trough", "provisional", x[lo], end)
    return None


def zero_crossings(x: Monthly) -> List[TurningPoint]:
    months = sorted(x)
    out = []
    for a, b in zip(months, months[1:]):
        if x[a] < 0 <= x[b]:
            out.append(TurningPoint(b, "cross_up", "event", x[b], b))
        elif x[a] >= 0 > x[b]:
            out.append(TurningPoint(b, "cross_down", "event", x[b], b))
    return out


def turning_points(x: Monthly, cfg: Optional[Dict] = None) -> List[TurningPoint]:
    cfg = cfg or {}
    conf = confirmed_turning_points(x, cfg.get("window", 5), cfg.get("min_phase", 5),
                                    cfg.get("min_cycle", 15), cfg.get("min_amplitude", 0.5))
    prov = provisional_turn(x, conf[-1] if conf else None, cfg.get("lookback", 12),
                            cfg.get("threshold", 0.5), cfg.get("confirm_months", 2))
    out = conf + ([prov] if prov else []) + zero_crossings(x)
    return sorted(out, key=lambda t: (t.month, t.kind))
