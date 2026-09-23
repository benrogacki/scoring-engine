"""Turn customer features into sub-scores, a composite score and a risk grade."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .config import GRADE_ORDER
from .models import Customer, CustomerFeatures, CustomerScore


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _linear_decline(value: float, full_until: float, zero_at: float) -> float:
    """100 while value <= full_until, falling linearly to 0 at zero_at."""
    if value <= full_until:
        return 100.0
    if value >= zero_at:
        return 0.0
    return 100.0 * (zero_at - value) / (zero_at - full_until)


def payment_score(f: CustomerFeatures, cfg: Dict[str, Any]) -> float:
    p = cfg["payment_history"]
    thin = float(p["thin_file_score"])
    if f.weighted_avg_days_late is None:
        return thin
    lateness = 100.0 * (1 - min(1.0, f.weighted_avg_days_late / p["days_late_floor"]))
    on_time = 100.0 * (f.on_time_rate or 0.0)
    w = p["on_time_weight"]
    score = (1 - w) * lateness + w * on_time
    trend = f.dpd_trend
    if trend is not None and trend > 0:
        score -= p["trend_max_penalty"] * min(1.0, trend / p["trend_full_penalty_days"])
    # Limited good history earns only partial credit above the thin-file baseline.
    confidence = min(1.0, f.paid_invoice_count / p["min_invoices_for_full_confidence"])
    if score > thin:
        score = thin + (score - thin) * confidence
    return _clamp(score)


def ageing_score(f: CustomerFeatures, cfg: Dict[str, Any]) -> float:
    if f.outstanding <= 0:
        return 100.0
    a = cfg["ageing"]
    index = sum(f.ageing.get(b, 0.0) / f.outstanding * w for b, w in a["bucket_weights"].items())
    score = 100.0 * (1 - index) - a["disputed_penalty"] * (f.disputed_amount / f.outstanding)
    return _clamp(score)


def concentration_score(f: CustomerFeatures, cfg: Dict[str, Any]) -> float:
    c = cfg["concentration"]
    share = _linear_decline(f.share_of_portfolio, 0.0, c["max_portfolio_share"])
    if f.limit_utilisation is None:
        return share
    util = _linear_decline(f.limit_utilisation, c["utilisation_comfortable"], c["utilisation_breach"])
    return (share + util) / 2


def grade_for(score: float, cfg: Dict[str, Any]) -> str:
    for band in cfg["grades"]:
        if score >= band["min_score"]:
            return band["grade"]
    return GRADE_ORDER[-1]


def grade_label(grade: str, cfg: Dict[str, Any]) -> str:
    return next((g["label"] for g in cfg["grades"] if g["grade"] == grade), "")


def _worse(grade: str, cap: str) -> str:
    return grade if GRADE_ORDER.index(grade) >= GRADE_ORDER.index(cap) else cap


def apply_overrides(grade: str, f: CustomerFeatures, cfg: Dict[str, Any]) -> Tuple[str, List[str]]:
    o = cfg["overrides"]
    notes = []
    severe = f.ageing.get("90_plus", 0.0)
    if f.outstanding > 0 and severe >= o["materiality"]:
        share = severe / f.outstanding
        cap = o["severe_arrears_cap"] if share >= o["severe_arrears_share"] else o["any_90_plus_cap"]
        if _worse(grade, cap) != grade:
            notes.append(f"Grade capped at {cap}: {share:.0%} of balance is 90+ days overdue")
            grade = cap
    if f.limit_utilisation is not None and f.limit_utilisation >= o["limit_breach_utilisation"]:
        cap = o["limit_breach_cap"]
        if _worse(grade, cap) != grade:
            notes.append(f"Grade capped at {cap}: balance is {f.limit_utilisation:.0%} of credit limit")
            grade = cap
    return grade, notes


def explain(f: CustomerFeatures, cfg: Dict[str, Any]) -> List[str]:
    """Plain-English risk drivers for the scorecard."""
    reasons: List[str] = []
    if f.weighted_avg_days_late is None:
        reasons.append("Thin file: no payment history in lookback window")
    else:
        if f.weighted_avg_days_late >= 1:
            reasons.append(f"Pays on average {f.weighted_avg_days_late:.0f} days late")
        if f.on_time_rate is not None and f.on_time_rate < 0.8:
            reasons.append(f"Only {f.on_time_rate:.0%} of invoice value paid on time")
        if f.paid_invoice_count < cfg["payment_history"]["min_invoices_for_full_confidence"]:
            reasons.append(f"Limited history ({f.paid_invoice_count} settled invoices)")
    trend = f.dpd_trend
    if trend is not None and trend >= 5:
        reasons.append(f"Deteriorating: paying {trend:.0f} days later than prior period")
    elif trend is not None and trend <= -5:
        reasons.append(f"Improving: paying {-trend:.0f} days sooner than prior period")
    if f.outstanding > 0:
        severe = f.ageing.get("90_plus", 0.0)
        late = f.ageing.get("61_90", 0.0) + severe
        if severe > 0:
            reasons.append(f"{late / f.outstanding:.0%} of balance is 60+ days overdue ({severe / f.outstanding:.0%} is 90+)")
        elif late > 0:
            reasons.append(f"{late / f.outstanding:.0%} of balance is 60+ days overdue")
        if f.disputed_amount > 0:
            reasons.append(f"{f.disputed_amount:,.0f} in dispute")
    if f.share_of_portfolio >= cfg["concentration"]["max_portfolio_share"] / 2:
        reasons.append(f"Concentration: {f.share_of_portfolio:.1%} of total receivables")
    if f.limit_utilisation is not None and f.limit_utilisation > 1.0:
        reasons.append(f"Over credit limit ({f.limit_utilisation:.0%} utilised)")
    elif f.credit_limit <= 0 and f.outstanding > 0:
        reasons.append("No credit limit on file")
    return reasons


def score_customer(customer: Customer, f: CustomerFeatures, cfg: Dict[str, Any]) -> CustomerScore:
    ps, ag, cs = payment_score(f, cfg), ageing_score(f, cfg), concentration_score(f, cfg)
    w = cfg["weights"]
    composite = round(w["payment"] * ps + w["ageing"] * ag + w["concentration"] * cs, 1)
    grade, override_notes = apply_overrides(grade_for(composite, cfg), f, cfg)
    return CustomerScore(
        customer=customer,
        features=f,
        payment_score=round(ps, 1),
        ageing_score=round(ag, 1),
        concentration_score=round(cs, 1),
        composite_score=composite,
        grade=grade,
        reasons=override_notes + explain(f, cfg),
    )


def portfolio_hhi(shares: List[float]) -> Optional[float]:
    """Herfindahl-Hirschman index of receivables concentration (0-10,000)."""
    if not shares:
        return None
    return round(sum((s * 100) ** 2 for s in shares), 0)
