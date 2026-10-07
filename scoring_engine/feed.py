"""The credit feed: what downstream systems read from a scoring run.

A versioned JSON contract for the ERP (credit holds, limit changes), collections
tooling (worklist order and actions) and BI. Consumers should check ``schema``
and reject a version they do not understand. Every customer carries the run's
backtest verdict and data-health status, so a consumer can refuse to act on a
run whose data failed checks or whose grades are not evidenced.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from .engine import PortfolioResult
from .health import now_utc

SCHEMA = "scoring_engine/credit_feed@1"


def credit_hold(s, cfg: Mapping[str, Any]) -> bool:
    """Stop new credit: grade E, or a material balance 90+ days overdue."""
    severe = s.features.ageing.get("90_plus", 0.0)
    return s.grade == "E" or severe >= cfg["overrides"]["materiality"]


def build_feed(result: PortfolioResult, cfg: Mapping[str, Any], *, source: Mapping[str, Any],
               health_status: str, backtest: Optional[Mapping[str, Any]], fingerprint: str,
               changes: Optional[List[Mapping[str, Any]]] = None) -> Dict[str, Any]:
    customers = []
    for s in sorted(result.scores, key=lambda s: s.customer.customer_id):
        f = s.features
        customers.append({
            "customer_id": s.customer.customer_id,
            "customer_name": s.customer.name,
            "grade": s.grade,
            "score": s.composite_score,
            "sub_scores": {"payment": s.payment_score, "ageing": s.ageing_score, "concentration": s.concentration_score},
            "outstanding": round(f.outstanding, 2),
            "overdue": round(f.overdue, 2),
            "oldest_days_overdue": f.oldest_days_overdue,
            "credit_limit": s.customer.credit_limit,
            "recommended_limit": s.recommended_limit,
            "limit_action": s.limit_action.split(" - ")[0].split(" (")[0],
            "over_limit": f.limit_utilisation is not None and f.limit_utilisation > 1,
            "credit_hold": credit_hold(s, cfg),
            "collection": {"tier": s.collection_tier or None, "rank": s.collection_rank,
                           "action": s.collection_action or None},
            "risk_drivers": s.reasons,
        })
    sm = result.summary
    return {
        "schema": SCHEMA,
        "as_of": result.as_of.isoformat(),
        "generated_at": now_utc(),
        "fingerprint": fingerprint,
        "source": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in source.items()},
        "data_health": health_status,
        "backtest": {k: backtest.get(k) for k in ("verdict", "auc", "gini", "monotonic", "observations", "bads")}
        if backtest else None,
        "portfolio": {
            "customers": sm["customers"],
            "total_outstanding": sm["total_outstanding"],
            "total_overdue": sm["total_overdue"],
            "ar_weighted_score": sm["ar_weighted_score"],
            "grades": {g: d["customers"] for g, d in sm["by_grade"].items()},
            "collection_tiers": sm["collection_tiers"],
            "credit_holds": sum(1 for c in customers if c["credit_hold"]),
        },
        "changes": list(changes or []),
        "customers": customers,
    }
