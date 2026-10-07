"""Data sources for the scoring engine: CSV files, NetSuite and Databricks.

Every source returns raw dict rows that go through the same loader
(``rows_to_invoices`` / ``rows_to_customers``) so validation is identical.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

CANONICAL_LEDGER = [
    "invoice_id", "customer_id", "invoice_date", "due_date", "amount",
    "amount_paid", "paid_date", "disputed",
]
CANONICAL_CUSTOMERS = ["customer_id", "customer_name", "credit_limit", "payment_terms_days", "industry"]


def write_rows_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Dump raw source rows to CSV (for audit, or to re-run offline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: List[str] = []
    for r in rows:
        for k in r.keys():
            if k not in fields:
                fields.append(k)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields or CANONICAL_LEDGER)
        writer.writeheader()
        writer.writerows(rows)
