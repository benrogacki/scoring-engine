"""Backtest: did the grades separate customers who went on to pay badly?

The engine is re-run as at several past dates using only what was known then
(invoices raised and payments received by that date). Each scored customer is
then followed for ``horizon_days`` to see whether any invoice crossed
``bad_days_past_due`` unpaid. A score earns trust only if:

* bad rates rise from grade A to grade E (monotonic), and
* the composite score ranks bad customers below good ones (AUC / Gini).

The result carries a verdict and is shown next to the scores, so nobody acts on
a scorecard the ledger's own history does not back.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Mapping, Optional

from .config import GRADE_ORDER
from .models import Customer, Invoice


@dataclass
class Backtest:
    points: List[str]
    horizon_days: int
    bad_days_past_due: int
    observations: int = 0
    bads: int = 0
    by_grade: Dict[str, Dict[str, float]] = field(default_factory=dict)
    auc: Optional[float] = None
    gini: Optional[float] = None
    monotonic: Optional[bool] = None
    verdict: str = "insufficient data"
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def went_bad(invoices: List[Invoice], t: date, horizon_days: int, dpd: int) -> bool:
    """True if any invoice crossed ``dpd`` days past due, still unpaid, within (t, t + horizon]."""
    end = t + timedelta(days=horizon_days)
    for inv in invoices:
        crossed = inv.due_date + timedelta(days=dpd)
        if not (t < crossed <= end):
            continue
        if inv.paid_date is None and inv.is_settled:
            continue  # closed without a payment date (e.g. written off): outcome unknown
        if inv.paid_date is None or inv.paid_date > crossed:
            return True
    return False


def auc_score(scores_bad: List[float], scores_good: List[float]) -> Optional[float]:
    """Probability a random bad customer scored below a random good one (ties count half)."""
    if not scores_bad or not scores_good:
        return None
    wins = 0.0
    for b in scores_bad:
        for g in scores_good:
            wins += 1.0 if b < g else 0.5 if b == g else 0.0
    return wins / (len(scores_bad) * len(scores_good))


def backtest_points(invoices: List[Invoice], as_of: date, cfg: Mapping[str, Any]) -> List[date]:
    b = cfg["backtest"]
    if not invoices:
        return []
    earliest = min(i.invoice_date for i in invoices)
    latest_start = as_of - timedelta(days=b["horizon_days"])
    points = []
    for k in range(b["points"]):
        t = latest_start - timedelta(days=k * b["step_days"])
        if (t - earliest).days >= b["min_history_days"]:
            points.append(t)
    return sorted(points)


def run_backtest(
    invoices: List[Invoice], customers: Dict[str, Customer], as_of: date, cfg: Mapping[str, Any]
) -> Backtest:
    from . import engine  # local import: engine imports nothing from here

    b = cfg["backtest"]
    points = backtest_points(invoices, as_of, cfg)
    result = Backtest(points=[p.isoformat() for p in points], horizon_days=b["horizon_days"],
                      bad_days_past_due=b["bad_days_past_due"])
    if not points:
        result.note = (f"Needs {b['min_history_days']} days of history before a backtest date plus "
                       f"{b['horizon_days']} days of outcome; the ledger is too short.")
        return result

    by_customer: Dict[str, List[Invoice]] = defaultdict(list)
    for inv in invoices:
        by_customer[inv.customer_id].append(inv)

    counts: Dict[str, List[int]] = {g: [0, 0] for g in GRADE_ORDER}  # [observed, bad]
    bad_scores, good_scores = [], []
    for t in points:
        run = engine.run(invoices, customers, t, dict(cfg))
        for s in run.scores:
            if s.features.outstanding <= 0:
                continue  # nothing at risk on that date
            bad = went_bad(by_customer[s.customer.customer_id], t, b["horizon_days"], b["bad_days_past_due"])
            counts[s.grade][0] += 1
            counts[s.grade][1] += int(bad)
            (bad_scores if bad else good_scores).append(s.composite_score)

    result.observations = len(bad_scores) + len(good_scores)
    result.bads = len(bad_scores)
    result.by_grade = {
        g: {"observations": n, "bads": k, "bad_rate": round(k / n, 4) if n else None}
        for g, (n, k) in counts.items()
    }
    auc = auc_score(bad_scores, good_scores)
    result.auc = round(auc, 3) if auc is not None else None
    result.gini = round(2 * auc - 1, 3) if auc is not None else None
    graded = [(g, v["bad_rate"]) for g, v in result.by_grade.items() if v["observations"] >= b["min_grade_observations"]]
    tol = b["monotonic_tolerance"]
    reversals = [f"{g1} {r1:.0%} > {g2} {r2:.0%}" for (g1, r1), (g2, r2) in zip(graded, graded[1:]) if r2 < r1]
    # Small reversals between neighbouring grades are expected from sampling noise.
    result.monotonic = all(r2 >= r1 - tol for (_, r1), (_, r2) in zip(graded, graded[1:])) if len(graded) >= 2 else None

    if result.observations < b["min_observations"] or result.bads < b["min_bads"]:
        result.verdict = "insufficient data"
        result.note = (f"{result.observations} customer-dates and {result.bads} bad outcomes; needs at least "
                       f"{b['min_observations']} and {b['min_bads']} to judge.")
    elif result.auc >= b["auc_evidenced"] and result.monotonic is not False:
        result.verdict = "evidenced"
        result.note = "Lower grades went bad more often, and the score ranks bad customers below good ones."
    elif result.auc >= b["auc_evidenced"]:
        result.verdict = "weak"
        result.note = "The score ranks bad customers below good ones, but bad rates do not rise steadily from A to E."
    elif result.auc >= b["auc_weak"]:
        result.verdict = "weak"
        result.note = "The score separates good from bad customers only modestly; review weights before relying on limits."
    else:
        result.verdict = "not evidenced"
        result.note = "The score does not separate customers who went bad; do not use the grades for decisions until recalibrated."
    if reversals and result.verdict != "insufficient data":
        result.note += " Reversals: " + "; ".join(reversals) + "."
    return result
