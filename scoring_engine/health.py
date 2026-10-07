"""Data health: is the extract complete, fresh and internally consistent?

The credit equivalent of a source-status panel. Every run records where the
ledger came from and when, then checks it before anyone acts on the scores:
stale extracts, duplicated invoices, impossible dates, customers missing from
the master, and (optionally) a control total from the ERP's AR ageing report.
A ``fail`` stops scheduled runs from publishing.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .models import Customer, Invoice

ORDER = {"ok": 0, "info": 0, "warn": 1, "fail": 2}


def _check(cid: str, label: str, status: str, detail: str) -> Dict[str, str]:
    return {"id": cid, "label": label, "status": status, "detail": detail}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def source_info(kind: str, label: str, invoices: List[Invoice], master: Mapping[str, Customer],
                extracted_at: Optional[str] = None) -> Dict[str, Any]:
    paid = [i.paid_date for i in invoices if i.paid_date]
    return {
        "kind": kind,
        "label": label,
        "extracted_at": extracted_at or now_utc(),
        "invoice_rows": len(invoices),
        "customer_rows": len(master),
        "first_invoice_date": min((i.invoice_date for i in invoices), default=None),
        "latest_invoice_date": max((i.invoice_date for i in invoices), default=None),
        "latest_payment_date": max(paid, default=None),
    }


def check_data(invoices: List[Invoice], master: Mapping[str, Customer], as_of: date, cfg: Mapping[str, Any],
               control_total: Optional[float] = None) -> List[Dict[str, str]]:
    h = cfg["health"]
    checks: List[Dict[str, str]] = []
    if not invoices:
        return [_check("invoices", "Invoices loaded", "fail", "The extract returned no invoices.")]
    checks.append(_check("invoices", "Invoices loaded", "ok", f"{len(invoices):,} invoices for "
                         f"{len({i.customer_id for i in invoices}):,} customers."))

    in_scope = [i for i in invoices if i.invoice_date <= as_of]
    latest_inv = max((i.invoice_date for i in in_scope), default=None)
    latest_pay = max((i.paid_date for i in in_scope if i.paid_date and i.paid_date <= as_of), default=None)
    stale = h["stale_days"]
    if latest_inv is None:
        checks.append(_check("freshness", "Extract is current", "fail", f"No invoices dated on or before {as_of}."))
    else:
        gaps = []
        if (as_of - latest_inv).days > stale:
            gaps.append(f"newest invoice is {latest_inv} ({(as_of - latest_inv).days} days before {as_of})")
        if latest_pay and (as_of - latest_pay).days > stale:
            gaps.append(f"newest payment is {latest_pay} ({(as_of - latest_pay).days} days before {as_of})")
        checks.append(_check("freshness", "Extract is current", "warn" if gaps else "ok",
                             ("Possibly stale: " + "; ".join(gaps) + ".") if gaps else
                             f"Newest invoice {latest_inv}, newest payment {latest_pay or 'none'}."))

    future = [i for i in invoices if i.invoice_date > as_of]
    if future:
        checks.append(_check("future", "Invoices after the scoring date", "info",
                             f"{len(future)} invoices dated after {as_of} are ignored for this run."))

    dupes = [k for k, n in Counter(i.invoice_id for i in invoices).items() if n > 1]
    checks.append(_check("duplicates", "No duplicate invoices", "warn" if dupes else "ok",
                         f"{len(dupes)} invoice IDs appear more than once (e.g. {', '.join(dupes[:3])}); "
                         "balances may be double counted." if dupes else "Every invoice ID is unique."))

    bad_dates = [i for i in invoices if i.due_date < i.invoice_date]
    checks.append(_check("dates", "Due dates after invoice dates", "warn" if bad_dates else "ok",
                         f"{len(bad_dates)} invoices are due before they were raised." if bad_dates
                         else "All due dates are on or after the invoice date."))

    over = [i for i in invoices if i.amount_paid - i.amount > 0.01]
    if over:
        checks.append(_check("overpaid", "Overpayments", "warn",
                             f"{len(over)} invoices show more paid than invoiced "
                             f"({sum(i.amount_paid - i.amount for i in over):,.2f} in total); check unapplied cash."))

    no_date = [i for i in invoices if i.is_settled and i.paid_date is None and i.amount > 0]
    if no_date:
        share = len(no_date) / len(invoices)
        checks.append(_check("paid_dates", "Settled invoices have payment dates",
                             "warn" if share > h["max_missing_paid_date_share"] else "info",
                             f"{len(no_date)} settled invoices ({share:.0%}) have no payment date, so their "
                             "payment behaviour is not measured."))

    ledger_ids = {i.customer_id for i in in_scope}
    missing = sorted(ledger_ids - set(master))
    if master:
        checks.append(_check("master", "Customers in the master file", "warn" if missing else "ok",
                             f"{len(missing)} debtors are not in the customer master (e.g. {', '.join(missing[:3])}); "
                             "they are scored with no credit limit." if missing else
                             "Every debtor is in the customer master."))
    else:
        checks.append(_check("master", "Customers in the master file", "warn",
                             "No customer master loaded: credit limits and terms default (30 days, no limit)."))

    open_total = sum(_open_at(i, as_of) for i in in_scope)
    if control_total is not None:
        diff = open_total - control_total
        tol = abs(control_total) * h["control_total_tolerance_pct"]
        checks.append(_check("control_total", "Agrees to AR ageing control total",
                             "ok" if abs(diff) <= max(tol, 1.0) else "fail",
                             f"Ledger open balance {open_total:,.2f} vs control total {control_total:,.2f} "
                             f"(difference {diff:+,.2f})."))
    else:
        checks.append(_check("control_total", "Agrees to AR ageing control total", "info",
                             f"Open balance {open_total:,.2f}. Pass --control-total with the ERP's AR ageing "
                             "total to reconcile automatically."))
    return checks


def _open_at(inv: Invoice, as_of: date) -> float:
    if inv.paid_date is not None and inv.paid_date > as_of:
        return inv.amount
    return inv.outstanding


def overall(checks: Iterable[Mapping[str, str]]) -> str:
    worst = max((ORDER.get(c["status"], 0) for c in checks), default=0)
    return {0: "ok", 1: "warn", 2: "fail"}[worst]


def fingerprint(*parts: Any) -> str:
    """Stable hash of a run's results, so a new run that changes nothing can be detected."""
    blob = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
