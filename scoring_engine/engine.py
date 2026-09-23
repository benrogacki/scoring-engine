"""End-to-end scoring pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List

from .collection import prioritise_collections
from .config import AGEING_BUCKETS, GRADE_ORDER
from .features import build_features
from .limits import recommend_limit
from .models import Customer, CustomerScore, Invoice
from .scoring import portfolio_hhi, score_customer


@dataclass
class PortfolioResult:
    as_of: date
    scores: List[CustomerScore]
    worklist: List[CustomerScore]
    summary: Dict[str, Any] = field(default_factory=dict)


def run(
    invoices: List[Invoice],
    customers: Dict[str, Customer],
    as_of: date,
    config: Dict[str, Any],
) -> PortfolioResult:
    features = build_features(invoices, customers, as_of, config)
    scores = [score_customer(customers[cid], f, config) for cid, f in features.items()]
    for s in scores:
        recommend_limit(s, config)
    worklist = prioritise_collections(scores, config)
    scores.sort(key=lambda s: (GRADE_ORDER.index(s.grade), -s.features.outstanding))
    return PortfolioResult(as_of=as_of, scores=scores, worklist=worklist, summary=summarise(scores))


def summarise(scores: List[CustomerScore]) -> Dict[str, Any]:
    total_ar = sum(s.features.outstanding for s in scores)
    ageing = {b: sum(s.features.ageing.get(b, 0.0) for s in scores) for b in AGEING_BUCKETS}
    overdue = sum(s.features.overdue for s in scores)
    by_grade = {
        g: {
            "customers": sum(1 for s in scores if s.grade == g),
            "outstanding": round(sum(s.features.outstanding for s in scores if s.grade == g), 2),
        }
        for g in GRADE_ORDER
    }
    ranked = sorted(scores, key=lambda s: -s.features.outstanding)
    top10 = sum(s.features.outstanding for s in ranked[:10])
    # AR-weighted average score: a single "health" number for the ledger.
    weighted_score = (
        sum(s.composite_score * s.features.outstanding for s in scores) / total_ar if total_ar else None
    )
    return {
        "customers": len(scores),
        "customers_with_balance": sum(1 for s in scores if s.features.outstanding > 0),
        "total_outstanding": round(total_ar, 2),
        "total_overdue": round(overdue, 2),
        "overdue_pct": round(overdue / total_ar, 4) if total_ar else 0.0,
        "ageing": {b: round(v, 2) for b, v in ageing.items()},
        "by_grade": by_grade,
        "ar_weighted_score": round(weighted_score, 1) if weighted_score is not None else None,
        "hhi": portfolio_hhi([s.features.share_of_portfolio for s in scores]),
        "top10_share": round(top10 / total_ar, 4) if total_ar else 0.0,
        "over_limit_customers": sum(
            1 for s in scores if s.features.limit_utilisation is not None and s.features.limit_utilisation > 1
        ),
        "limit_actions": _count(s.limit_action.split(" - ")[0] for s in scores),
        "collection_tiers": _count(s.collection_tier for s in scores if s.collection_tier),
    }


def _count(values) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return dict(sorted(counts.items()))
