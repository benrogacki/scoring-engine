"""Credit limit recommendations.

The recommended limit is the exposure a customer needs to trade on their terms,
scaled by how much risk the grade justifies:

    limit = avg monthly sales x (payment terms + buffer days) / 30 x grade multiplier

Increases are capped per review so limits move in steps finance can sign off.
"""
from __future__ import annotations

from typing import Any, Dict

from .models import CustomerScore


def _round_to(value: float, step: float) -> float:
    if step <= 0:
        return round(value, 2)
    return round(value / step) * step


def recommend_limit(score: CustomerScore, cfg: Dict[str, Any]) -> None:
    c = cfg["credit_limits"]
    f = score.features
    current = score.customer.credit_limit
    multiplier = c["grade_multipliers"][score.grade]

    if multiplier <= 0:
        score.recommended_limit = 0.0
        score.limit_action = "Suspend credit (cash with order)"
        return
    if f.avg_monthly_sales <= 0:
        score.recommended_limit = current
        score.limit_action = "Review (no sales in lookback)"
        return

    need = f.avg_monthly_sales * (score.customer.payment_terms_days + c["buffer_days"]) / 30.0
    recommended = need * multiplier
    concentrated = f.share_of_portfolio >= c["block_increase_at_portfolio_share"]
    if current > 0:
        may_increase = score.grade in c["increase_allowed_grades"] and not concentrated
        ceiling = 1 + c["max_increase_pct"] if may_increase else 1.0
        recommended = min(recommended, current * ceiling)
    recommended = max(0.0, _round_to(recommended, c["rounding"]))

    tol = c["tolerance_pct"]
    if current <= 0:
        action = "Set limit"
    elif recommended > current * (1 + tol):
        action = "Increase"
    elif recommended < current * (1 - tol):
        action = "Reduce"
    else:
        action, recommended = "Maintain", current
        if concentrated:
            action += " (concentration cap)"
    if current > 0 and f.outstanding > current:
        action += " - currently over limit"
    score.recommended_limit = recommended
    score.limit_action = action
