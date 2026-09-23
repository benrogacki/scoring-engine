"""Derive per-customer risk features from the debtor ledger."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from .config import AGEING_BUCKETS
from .models import Customer, CustomerFeatures, Invoice

DAYS_PER_MONTH = 30.4375


def ageing_bucket(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "1_30"
    if days_overdue <= 60:
        return "31_60"
    if days_overdue <= 90:
        return "61_90"
    return "90_plus"


def _weighted_mean(pairs: List[tuple]) -> Optional[float]:
    total_weight = sum(w for _, w in pairs)
    if total_weight <= 0:
        return None
    return sum(v * w for v, w in pairs) / total_weight


def build_features(
    invoices: List[Invoice],
    customers: Dict[str, Customer],
    as_of: date,
    config: Dict[str, Any],
) -> Dict[str, CustomerFeatures]:
    lookback_start = as_of - timedelta(days=round(config["lookback_months"] * DAYS_PER_MONTH))
    recent_start = as_of - timedelta(days=round(config["recent_window_months"] * DAYS_PER_MONTH))
    grace = config["grace_days"]

    by_customer: Dict[str, List[Invoice]] = defaultdict(list)
    for inv in invoices:
        if inv.invoice_date <= as_of:
            by_customer[inv.customer_id].append(inv)

    features: Dict[str, CustomerFeatures] = {}
    for cid, customer in customers.items():
        f = CustomerFeatures(customer_id=cid, ageing={b: 0.0 for b in AGEING_BUCKETS})
        f.credit_limit = customer.credit_limit
        lateness_all, lateness_recent, lateness_prior = [], [], []
        on_time_value = assessed_value = 0.0
        first_invoice: Optional[date] = None

        for inv in by_customer.get(cid, []):
            first_invoice = inv.invoice_date if first_invoice is None else min(first_invoice, inv.invoice_date)
            if inv.invoice_date >= lookback_start:
                f.sales_lookback += inv.amount

            # Treat as open if unsettled today, or settled only after the as-of date.
            paid_after_as_of = inv.paid_date is not None and inv.paid_date > as_of
            is_open = not inv.is_settled or paid_after_as_of
            open_amount = inv.amount if paid_after_as_of else inv.outstanding

            if is_open and open_amount > 0:
                days = inv.days_overdue(as_of)
                f.ageing[ageing_bucket(days)] += open_amount
                f.outstanding += open_amount
                if days > 0:
                    f.overdue += open_amount
                    f.oldest_days_overdue = max(f.oldest_days_overdue, days)
                if inv.disputed:
                    f.disputed_amount += open_amount

            # Payment behaviour. Settled invoices use actual days late; open invoices
            # already past due count as "at least this late" so non-payers are not
            # mistaken for thin files.
            if not is_open and inv.paid_date is not None and inv.paid_date >= lookback_start:
                days_late, event_date = inv.days_late_paid(), inv.paid_date
                f.paid_invoice_count += 1
            elif is_open and inv.due_date >= lookback_start and inv.days_overdue(as_of) > grace:
                days_late, event_date = inv.days_overdue(as_of), as_of
            else:
                continue
            late = max(0, days_late)
            lateness_all.append((late, inv.amount))
            (lateness_recent if event_date >= recent_start else lateness_prior).append((late, inv.amount))
            assessed_value += inv.amount
            if days_late <= grace:
                on_time_value += inv.amount

        f.weighted_avg_days_late = _weighted_mean(lateness_all)
        f.recent_days_late = _weighted_mean(lateness_recent)
        f.prior_days_late = _weighted_mean(lateness_prior)
        f.on_time_rate = on_time_value / assessed_value if assessed_value else None
        if first_invoice is not None:
            span = (as_of - max(first_invoice, lookback_start)).days / DAYS_PER_MONTH
            f.months_observed = min(float(config["lookback_months"]), max(1.0, span))
        features[cid] = f

    total_ar = sum(f.outstanding for f in features.values())
    for f in features.values():
        f.share_of_portfolio = f.outstanding / total_ar if total_ar else 0.0
        f.limit_utilisation = f.outstanding / f.credit_limit if f.credit_limit > 0 else None
    return features
