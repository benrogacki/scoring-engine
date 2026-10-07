"""What changed since the previous run: the moves a credit controller acts on.

Compares two scorecards (this run and the last published one) and lists
regrades, new escalations, customers newly over their limit, limit-action
changes, and customers that appeared or dropped out, most severe first.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .config import GRADE_ORDER

SEVERITY = {"escalated": 0, "downgrade": 1, "over_limit": 2, "limit_action": 3, "new": 4,
            "upgrade": 5, "de_escalated": 6, "back_within_limit": 7, "gone": 8}


def read_scorecard(path: Path) -> Dict[str, Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["customer_id"]: r for r in csv.DictReader(fh)}


def _f(v: Optional[str]) -> float:
    try:
        return float(v) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0


def _over(r: Mapping[str, str]) -> bool:
    return _f(r.get("limit_utilisation_pct")) > 100


def _base_action(r: Mapping[str, str]) -> str:
    return (r.get("limit_action") or "").split(" - ")[0].split(" (")[0]


def diff_scorecards(old: Mapping[str, Mapping[str, str]], new: Mapping[str, Mapping[str, str]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    def add(kind: str, r: Mapping[str, str], detail: str) -> None:
        out.append({"kind": kind, "customer_id": r["customer_id"], "customer_name": r.get("customer_name", ""),
                    "grade": r.get("grade", ""), "outstanding": _f(r.get("outstanding")), "detail": detail})

    for cid, n in new.items():
        o = old.get(cid)
        if o is None:
            add("new", n, f"New on the ledger: grade {n['grade']}, balance {_f(n.get('outstanding')):,.0f}")
            continue
        go, gn = GRADE_ORDER.index(o["grade"]), GRADE_ORDER.index(n["grade"])
        if gn > go:
            add("downgrade", n, f"Downgraded {o['grade']} → {n['grade']} (score {_f(o['composite_score']):.1f} → "
                                f"{_f(n['composite_score']):.1f})")
        elif gn < go:
            add("upgrade", n, f"Upgraded {o['grade']} → {n['grade']} (score {_f(o['composite_score']):.1f} → "
                              f"{_f(n['composite_score']):.1f})")
        if n.get("collection_tier") == "P1" and o.get("collection_tier") != "P1":
            add("escalated", n, f"New P1 escalation ({o.get('collection_tier') or 'not overdue'} → P1): "
                                f"{_f(n.get('overdue')):,.0f} overdue, oldest {n.get('oldest_days_overdue')} days")
        elif o.get("collection_tier") == "P1" and n.get("collection_tier") != "P1":
            add("de_escalated", n, f"No longer P1 (now {n.get('collection_tier') or 'not overdue'})")
        if _over(n) and not _over(o):
            add("over_limit", n, f"Now over limit: {_f(n.get('limit_utilisation_pct')):.0f}% of "
                                 f"{_f(n.get('credit_limit')):,.0f}")
        elif _over(o) and not _over(n):
            add("back_within_limit", n, "Back within credit limit")
        if _base_action(n) != _base_action(o):
            add("limit_action", n, f"Limit recommendation {_base_action(o) or 'none'} → {_base_action(n)} "
                                   f"({_f(n.get('credit_limit')):,.0f} → {_f(n.get('recommended_limit')):,.0f})")
    for cid, o in old.items():
        if cid not in new:
            add("gone", o, "No longer on the ledger")
    out.sort(key=lambda c: (SEVERITY[c["kind"]], -c["outstanding"]))
    return out


def summarise_changes(changes: List[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for c in changes:
        counts[c["kind"]] = counts.get(c["kind"], 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: SEVERITY[kv[0]]))


def changes_markdown(changes: List[Mapping[str, Any]], previous_as_of: Optional[str], limit: int = 50) -> str:
    if previous_as_of is None:
        return "No previous run to compare against.\n"
    if not changes:
        return f"No changes since the run as at {previous_as_of}.\n"
    lines = [f"Changes since the run as at {previous_as_of}:", ""]
    lines += [f"- **{c['customer_name']}** ({c['customer_id']}): {c['detail']}" for c in changes[:limit]]
    if len(changes) > limit:
        lines.append(f"- … and {len(changes) - limit} more (see changes.json)")
    return "\n".join(lines) + "\n"
