"""One scoring run end to end, shared by the CLI, CI and the Databricks job.

load → health checks → score → backtest → compare with the previous run →
write reports, credit feed, dashboard and the data fingerprint.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from . import engine
from .backtest import run_backtest
from .changes import changes_markdown, diff_scorecards, read_scorecard, summarise_changes
from .config import GRADE_ORDER
from .dashboard import write_dashboard
from .feed import build_feed
from .health import check_data, fingerprint, overall
from .loader import merge_customers
from .models import Customer, Invoice
from .report import scorecard_rows, worklist_rows, write_outputs

FINGERPRINT_FILE = "data_fingerprint.txt"
STATUS_LABEL = {"ok": "passed", "warn": "passed with warnings", "fail": "FAILED"}


@dataclass
class RunOutcome:
    result: engine.PortfolioResult
    health: List[Dict[str, str]]
    health_status: str
    backtest: Optional[Dict[str, Any]]
    changes: Optional[List[Dict[str, Any]]]
    previous_as_of: Optional[str]
    fingerprint: str
    paths: Dict[str, Path] = field(default_factory=dict)


def previous_run(prev_dir: Optional[Path]):
    """(as_of, scorecard) of an earlier output folder, or (None, None) if there isn't one."""
    if prev_dir is None:
        return None, None
    card, summary = Path(prev_dir) / "scorecard.csv", Path(prev_dir) / "portfolio_summary.json"
    if not card.exists():
        return None, None
    as_of = json.loads(summary.read_text(encoding="utf-8")).get("as_of") if summary.exists() else None
    return as_of, read_scorecard(card)


def score_run(
    invoices: List[Invoice],
    master: Mapping[str, Customer],
    as_of: date,
    cfg: Mapping[str, Any],
    source: Mapping[str, Any],
    *,
    previous: Optional[Mapping[str, Mapping[str, str]]] = None,
    previous_as_of: Optional[str] = None,
    control_total: Optional[float] = None,
    backtest: bool = True,
) -> RunOutcome:
    checks = check_data(invoices, master, as_of, cfg, control_total)
    status = overall(checks)
    customers = merge_customers(invoices, dict(master))
    result = engine.run(invoices, customers, as_of, dict(cfg))
    bt = run_backtest(invoices, customers, as_of, cfg).to_dict() if backtest else None
    card = scorecard_rows(result, dict(cfg))
    changes = None
    if previous is not None:
        current = {str(r["customer_id"]): {k: str(v) for k, v in r.items()} for r in card}
        changes = diff_scorecards(previous, current)
    fp = fingerprint(card, worklist_rows(result), status)
    return RunOutcome(result, checks, status, bt, changes, previous_as_of if previous is not None else None, fp)


def run_markdown(run: RunOutcome, source: Mapping[str, Any]) -> str:
    lines = ["", "## Data health", "",
             f"Source: {source.get('label')} · extracted {source.get('extracted_at')} · "
             f"checks **{STATUS_LABEL[run.health_status]}**", "",
             "| Check | Status | Detail |", "|---|---|---|"]
    lines += [f"| {c['label']} | {c['status']} | {c['detail']} |" for c in run.health]
    bt = run.backtest
    lines += ["", "## Backtest", ""]
    if bt:
        auc = f"AUC {bt['auc']:.2f}, Gini {bt['gini']:.2f}" if bt.get("auc") is not None else "AUC n/a"
        lines += [f"**{bt['verdict']}**: {bt['note']} ({auc}; {bt['observations']} customer-dates, "
                  f"{bt['bads']} went {bt['bad_days_past_due']}+ days overdue within {bt['horizon_days']} days; "
                  f"scored at {', '.join(bt['points']) or 'no dates'}.)", "",
                  "| Grade | Observed | Went bad | Bad rate |", "|---|---:|---:|---:|"]
        for g in GRADE_ORDER:
            d = bt["by_grade"].get(g, {})
            rate = f"{d['bad_rate']:.0%}" if d.get("bad_rate") is not None else "–"
            lines.append(f"| {g} | {d.get('observations', 0)} | {d.get('bads', 0)} | {rate} |")
    else:
        lines.append("Skipped for this run.")
    lines += ["", "## Changes since the last run", "", changes_markdown(run.changes or [], run.previous_as_of)]
    return "\n".join(lines)


def write_run(run: RunOutcome, cfg: Mapping[str, Any], out_dir: Path, source: Mapping[str, Any],
              currency: str = "", label: Optional[str] = None) -> Dict[str, Path]:
    out_dir = Path(out_dir)
    paths = write_outputs(run.result, dict(cfg), out_dir)
    with open(paths["summary_md"], "a", encoding="utf-8") as fh:
        fh.write(run_markdown(run, source))
    feed = build_feed(run.result, cfg, source=source, health_status=run.health_status, backtest=run.backtest,
                      fingerprint=run.fingerprint, changes=run.changes)
    extra = {
        "feed": (out_dir / "credit_feed.json", feed),
        "health": (out_dir / "data_health.json", {"status": run.health_status, "source": source, "checks": run.health}),
        "backtest": (out_dir / "backtest.json", run.backtest),
        "changes": (out_dir / "changes.json", {"previous_as_of": run.previous_as_of, "changes": run.changes or [],
                                               "counts": summarise_changes(run.changes or [])}),
    }
    for key, (path, data) in extra.items():
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        paths[key] = path
    paths["fingerprint"] = out_dir / FINGERPRINT_FILE
    paths["fingerprint"].write_text(run.fingerprint + "\n", encoding="utf-8")
    paths["dashboard"] = write_dashboard(run.result, dict(cfg), out_dir / "dashboard.html",
                                         source=label or source.get("label", ""), currency=currency, run=run,
                                         source_info=source)
    run.paths = paths
    return paths


def run_log_row(run: RunOutcome, source: Mapping[str, Any]) -> Dict[str, Any]:
    """One row per run for a run-history table: what ran, on what data, and how it checked out."""
    sm = run.result.summary
    bt = run.backtest or {}
    counts = summarise_changes(run.changes or [])
    row: Dict[str, Any] = {
        "run_at": source.get("extracted_at"),
        "source": source.get("label"),
        "fingerprint": run.fingerprint,
        "data_health": run.health_status,
        "backtest_verdict": bt.get("verdict", "skipped"),
        "backtest_auc": bt.get("auc"),
        "customers": sm["customers"],
        "total_outstanding": sm["total_outstanding"],
        "overdue_pct": sm["overdue_pct"],
        "previous_as_of": run.previous_as_of or "",
        "changes": len(run.changes or []),
    }
    for g, d in sm["by_grade"].items():
        row[f"grade_{g.lower()}"] = d["customers"]
    for kind in ("escalated", "downgrade", "over_limit"):
        row[f"changes_{kind}"] = counts.get(kind, 0)
    return row


def job_summary(run: RunOutcome, source: Mapping[str, Any]) -> str:
    """Aggregate-only Markdown for CI job summaries (no customer names or balances by customer)."""
    sm = run.result.summary
    bt = run.backtest or {}
    counts = summarise_changes(run.changes or [])
    lines = [
        f"### Credit scoring as at {run.result.as_of.isoformat()}",
        "",
        f"- Source: {source.get('label')} (extracted {source.get('extracted_at')})",
        f"- Data health: **{STATUS_LABEL[run.health_status]}**"
        + "".join(f"\n  - {c['status']}: {c['label']} - {c['detail']}" for c in run.health if c["status"] in ("warn", "fail")),
        f"- Customers: {sm['customers']} · receivables {sm['total_outstanding']:,.0f} · overdue {sm['overdue_pct']:.1%}",
        "- Grades: " + ", ".join(f"{g} {d['customers']}" for g, d in sm["by_grade"].items()),
        "- Collections: " + (", ".join(f"{t} {n}" for t, n in sm["collection_tiers"].items()) or "nothing overdue"),
        f"- Backtest: {bt.get('verdict', 'skipped')}" + (f" (AUC {bt['auc']:.2f})" if bt.get("auc") is not None else ""),
        "- Changes since last run: " + (", ".join(f"{k.replace('_', ' ')} {n}" for k, n in counts.items()) or
                                        ("none" if run.previous_as_of else "no previous run")),
        f"- Fingerprint: `{run.fingerprint}`",
    ]
    return "\n".join(lines) + "\n"
