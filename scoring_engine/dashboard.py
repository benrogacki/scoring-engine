"""Build the interactive HTML dashboard from a scoring run.

The page embeds each customer's features plus the policy config, and re-runs the
scoring rules in the browser so the Policy tab can re-score the ledger live.
The Python engine stays the source of truth; ``py`` fields carry its results
so the two can be checked against each other.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .engine import PortfolioResult

TEMPLATE = Path(__file__).with_name("templates") / "dashboard.html"
STANDALONE_HEAD = (
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    "</head>\n<body>\n"
)


def _opt(value: Optional[float], digits: int = 4) -> Optional[float]:
    return None if value is None else round(value, digits)


def build_payload(result: PortfolioResult, config: Dict[str, Any], source: str = "", currency: str = "") -> Dict[str, Any]:
    customers = []
    for s in sorted(result.scores, key=lambda s: s.customer.customer_id):
        f = s.features
        customers.append(
            {
                "id": s.customer.customer_id,
                "name": s.customer.name,
                "industry": s.customer.industry,
                "terms": s.customer.payment_terms_days,
                "limit": s.customer.credit_limit,
                "f": {
                    "wadl": _opt(f.weighted_avg_days_late),
                    "otr": _opt(f.on_time_rate),
                    "recent": _opt(f.recent_days_late),
                    "prior": _opt(f.prior_days_late),
                    "paid": f.paid_invoice_count,
                    "out": round(f.outstanding, 2),
                    "ageing": {b: round(v, 2) for b, v in f.ageing.items()},
                    "overdue": round(f.overdue, 2),
                    "oldest": f.oldest_days_overdue,
                    "disputed": round(f.disputed_amount, 2),
                    "share": _opt(f.share_of_portfolio, 6),
                    "limit": f.credit_limit,
                    "util": _opt(f.limit_utilisation, 6),
                    "sales_m": round(f.avg_monthly_sales, 2),
                },
                "py": {
                    "score": s.composite_score,
                    "grade": s.grade,
                    "rec": s.recommended_limit,
                    "tier": s.collection_tier,
                    "rank": s.collection_rank,
                },
            }
        )
    return {
        "as_of": result.as_of.isoformat(),
        "source": source,
        "currency": currency,
        "config": config,
        "customers": customers,
    }


def render_dashboard(payload: Dict[str, Any], standalone: bool = True) -> str:
    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8").replace("__PAYLOAD__", data)
    return STANDALONE_HEAD + page + "\n</body>\n</html>\n" if standalone else page


def write_dashboard(
    result: PortfolioResult,
    config: Dict[str, Any],
    path: Path,
    source: str = "",
    currency: str = "",
    standalone: bool = True,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_dashboard(build_payload(result, config, source, currency), standalone), encoding="utf-8")
    return path
