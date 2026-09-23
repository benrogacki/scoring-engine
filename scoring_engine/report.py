"""Write scoring outputs: scorecard CSV, collections worklist, portfolio summary."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import AGEING_BUCKETS, GRADE_ORDER
from .engine import PortfolioResult
from .models import CustomerScore
from .scoring import grade_label

BUCKET_LABELS = {"current": "Not due", "1_30": "1-30", "31_60": "31-60", "61_90": "61-90", "90_plus": "90+"}


def _fmt(value: Optional[float], digits: int = 2) -> str:
    return "" if value is None else f"{value:.{digits}f}"


def scorecard_rows(result: PortfolioResult, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for s in result.scores:
        f = s.features
        row = {
            "customer_id": s.customer.customer_id,
            "customer_name": s.customer.name,
            "industry": s.customer.industry,
            "grade": s.grade,
            "grade_label": grade_label(s.grade, cfg),
            "composite_score": _fmt(s.composite_score, 1),
            "payment_score": _fmt(s.payment_score, 1),
            "ageing_score": _fmt(s.ageing_score, 1),
            "concentration_score": _fmt(s.concentration_score, 1),
            "outstanding": _fmt(f.outstanding),
            "overdue": _fmt(f.overdue),
        }
        for b in AGEING_BUCKETS:
            row[f"age_{b}"] = _fmt(f.ageing.get(b, 0.0))
        row.update(
            {
                "oldest_days_overdue": f.oldest_days_overdue,
                "disputed_amount": _fmt(f.disputed_amount),
                "share_of_portfolio_pct": _fmt(f.share_of_portfolio * 100),
                "avg_days_late": _fmt(f.weighted_avg_days_late, 1),
                "on_time_rate_pct": _fmt(f.on_time_rate * 100 if f.on_time_rate is not None else None, 1),
                "days_late_trend": _fmt(f.dpd_trend, 1),
                "settled_invoices": f.paid_invoice_count,
                "avg_monthly_sales": _fmt(f.avg_monthly_sales),
                "payment_terms_days": s.customer.payment_terms_days,
                "credit_limit": _fmt(s.customer.credit_limit),
                "limit_utilisation_pct": _fmt(
                    f.limit_utilisation * 100 if f.limit_utilisation is not None else None, 1
                ),
                "recommended_limit": _fmt(s.recommended_limit),
                "limit_change": _fmt(s.recommended_limit - s.customer.credit_limit),
                "limit_action": s.limit_action,
                "collection_tier": s.collection_tier,
                "collection_rank": s.collection_rank or "",
                "risk_drivers": "; ".join(s.reasons),
            }
        )
        rows.append(row)
    return rows


def worklist_rows(result: PortfolioResult) -> List[Dict[str, Any]]:
    rows = []
    for s in result.worklist:
        f = s.features
        rows.append(
            {
                "rank": s.collection_rank,
                "tier": s.collection_tier,
                "customer_id": s.customer.customer_id,
                "customer_name": s.customer.name,
                "grade": s.grade,
                "overdue": _fmt(f.overdue),
                "age_31_60": _fmt(f.ageing.get("31_60", 0.0)),
                "age_61_90": _fmt(f.ageing.get("61_90", 0.0)),
                "age_90_plus": _fmt(f.ageing.get("90_plus", 0.0)),
                "oldest_days_overdue": f.oldest_days_overdue,
                "disputed_amount": _fmt(f.disputed_amount),
                "priority_score": _fmt(s.collection_priority_score),
                "action": s.collection_action,
                "risk_drivers": "; ".join(s.reasons),
            }
        )
    return rows


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        if not rows:
            return
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _money(v: float) -> str:
    return f"{v:,.0f}"


def _pct(v: float) -> str:
    return f"{v:.1%}"


def summary_markdown(result: PortfolioResult, cfg: Dict[str, Any], top_n: int = 15) -> str:
    sm = result.summary
    total = sm["total_outstanding"] or 1.0
    lines = [
        f"# Debtor Ledger Credit-Risk Summary — as at {result.as_of.isoformat()}",
        "",
        "## Headline",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Customers scored | {sm['customers']} ({sm['customers_with_balance']} with a balance) |",
        f"| Total receivables | {_money(sm['total_outstanding'])} |",
        f"| Overdue | {_money(sm['total_overdue'])} ({_pct(sm['overdue_pct'])}) |",
        f"| AR-weighted credit score | {sm['ar_weighted_score'] if sm['ar_weighted_score'] is not None else 'n/a'} |",
        f"| Concentration (HHI) | {sm['hhi'] if sm['hhi'] is not None else 'n/a'} {_hhi_band(sm['hhi'])} |",
        f"| Top-10 debtor share | {_pct(sm['top10_share'])} |",
        f"| Customers over limit | {sm['over_limit_customers']} |",
        "",
        "## Ageing profile",
        "",
        "| Bucket | Balance | Share |",
        "|---|---:|---:|",
    ]
    for b in AGEING_BUCKETS:
        v = sm["ageing"][b]
        lines.append(f"| {BUCKET_LABELS[b]} | {_money(v)} | {_pct(v / total)} |")

    lines += ["", "## Risk grade distribution", "", "| Grade | Meaning | Customers | Balance | Share |", "|---|---|---:|---:|---:|"]
    for g in GRADE_ORDER:
        d = sm["by_grade"][g]
        lines.append(
            f"| {g} | {grade_label(g, cfg)} | {d['customers']} | {_money(d['outstanding'])} | {_pct(d['outstanding'] / total)} |"
        )

    lines += ["", "## Largest exposures", "", "| Customer | Grade | Balance | Share of AR | Limit used |", "|---|---|---:|---:|---:|"]
    for s in sorted(result.scores, key=lambda s: -s.features.outstanding)[:10]:
        f = s.features
        if f.outstanding <= 0:
            break
        used = _pct(f.limit_utilisation) if f.limit_utilisation is not None else "no limit"
        lines.append(f"| {s.customer.name} | {s.grade} | {_money(f.outstanding)} | {_pct(f.share_of_portfolio)} | {used} |")

    lines += ["", f"## Collections worklist (top {top_n})", ""]
    if result.worklist:
        lines += ["| # | Tier | Customer | Grade | Overdue | Oldest (days) | Action |", "|---:|---|---|---|---:|---:|---|"]
        for s in result.worklist[:top_n]:
            lines.append(
                f"| {s.collection_rank} | {s.collection_tier} | {s.customer.name} | {s.grade} | "
                f"{_money(s.features.overdue)} | {s.features.oldest_days_overdue} | {s.collection_action} |"
            )
    else:
        lines.append("No overdue balances.")

    changes = [s for s in result.scores if not s.limit_action.startswith("Maintain")]
    lines += ["", "## Credit limit recommendations", ""]
    if changes:
        lines += ["| Customer | Grade | Current | Recommended | Action |", "|---|---|---:|---:|---|"]
        for s in sorted(changes, key=lambda s: GRADE_ORDER.index(s.grade), reverse=True):
            lines.append(
                f"| {s.customer.name} | {s.grade} | {_money(s.customer.credit_limit)} | "
                f"{_money(s.recommended_limit)} | {s.limit_action} |"
            )
    else:
        lines.append("All limits appropriate — no changes recommended.")

    lines += [
        "",
        "## Method",
        "",
        f"Composite score (0-100, higher = lower risk) = "
        f"{cfg['weights']['payment']:.0%} payment history + {cfg['weights']['ageing']:.0%} ageing + "
        f"{cfg['weights']['concentration']:.0%} concentration/exposure, then policy caps "
        "(90+ arrears, limit breach). Payment history covers the last "
        f"{cfg['lookback_months']} months. See `scorecard.csv` for every customer's sub-scores and risk drivers.",
        "",
    ]
    return "\n".join(lines)


def _hhi_band(hhi: Optional[float]) -> str:
    if hhi is None:
        return ""
    if hhi < 1500:
        return "(diversified)"
    if hhi < 2500:
        return "(moderately concentrated)"
    return "(highly concentrated)"


def write_outputs(result: PortfolioResult, cfg: Dict[str, Any], out_dir: Path) -> Dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "scorecard": out_dir / "scorecard.csv",
        "worklist": out_dir / "collections_worklist.csv",
        "summary_md": out_dir / "portfolio_summary.md",
        "summary_json": out_dir / "portfolio_summary.json",
    }
    _write_csv(paths["scorecard"], scorecard_rows(result, cfg))
    _write_csv(paths["worklist"], worklist_rows(result))
    paths["summary_md"].write_text(summary_markdown(result, cfg), encoding="utf-8")
    payload = {"as_of": result.as_of.isoformat(), **result.summary}
    paths["summary_json"].write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return paths
