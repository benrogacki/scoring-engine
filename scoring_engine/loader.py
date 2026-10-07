"""Load and validate debtor ledger and customer master data.

Every source (CSV files, NetSuite SuiteQL, Databricks tables) produces plain
dict rows; ``rows_to_invoices`` / ``rows_to_customers`` turn them into model
objects with the same column aliasing and validation regardless of origin.
"""
from __future__ import annotations

import csv
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .models import Customer, Invoice

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S")
TRUE_VALUES = {"1", "true", "yes", "y", "t"}

# Accept common alternative column headings from ERP exports.
LEDGER_ALIASES = {
    "invoice_id": ("invoice_id", "invoice", "invoice_no", "invoice_number", "document_no", "tranid"),
    "customer_id": ("customer_id", "customer", "account", "account_code", "debtor_id", "entity"),
    "invoice_date": ("invoice_date", "document_date", "date", "trandate"),
    "due_date": ("due_date", "due", "duedate"),
    "amount": ("amount", "invoice_amount", "gross_amount", "total"),
    "amount_paid": ("amount_paid", "paid_amount", "paid"),
    # Open balance, as ERPs usually hold it; converted to amount_paid on load.
    "amount_remaining": ("amount_remaining", "amount_due", "outstanding", "balance", "amountremaining"),
    "paid_date": ("paid_date", "payment_date", "cleared_date", "last_payment_date"),
    "disputed": ("disputed", "in_dispute", "dispute"),
}
CUSTOMER_ALIASES = {
    "customer_id": ("customer_id", "customer", "account", "account_code", "debtor_id", "id"),
    "name": ("name", "customer_name", "account_name", "companyname"),
    "credit_limit": ("credit_limit", "limit", "creditlimit"),
    "payment_terms_days": ("payment_terms_days", "terms_days", "terms", "daysuntilnetdue"),
    "industry": ("industry", "sector", "segment", "category"),
}


class LedgerError(ValueError):
    """Raised when input data cannot be interpreted."""


def parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    value = str(value).strip()
    if not value:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise LedgerError(f"Unrecognised date: {value!r}")


def parse_amount(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return float(value)
    value = str(value).strip()
    if not value:
        return None
    negative = value.startswith("(") and value.endswith(")")
    cleaned = re.sub(r"[^0-9.\-]", "", value)
    if cleaned in ("", "-", "."):
        raise LedgerError(f"Unrecognised amount: {value!r}")
    number = float(cleaned)
    return -number if negative else number


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value if value is not None else "").strip().lower() in TRUE_VALUES


def _resolve_columns(header: Iterable[str], aliases: Dict[str, Tuple[str, ...]]) -> Dict[str, str]:
    normalised = {h.strip().lower().replace(" ", "_"): h for h in header}
    mapping = {}
    for canonical, options in aliases.items():
        for option in options:
            if option in normalised:
                mapping[canonical] = normalised[option]
                break
    return mapping


def _require(mapping: Dict[str, str], required: Iterable[str], source: str) -> None:
    missing = [c for c in required if c not in mapping]
    if missing:
        raise LedgerError(f"{source}: missing required column(s): {', '.join(missing)}")


def _getter(row: Mapping[str, Any], cols: Dict[str, str]):
    def get(key: str) -> Any:
        return row.get(cols[key]) if key in cols else None

    return get


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def rows_to_invoices(rows: Iterable[Mapping[str, Any]], source: str = "ledger", header: Optional[List[str]] = None) -> List[Invoice]:
    rows = iter(rows)
    first = None
    if header is None:
        first = next(rows, None)
        if first is None:
            return []
        header = list(first.keys())
    cols = _resolve_columns(header, LEDGER_ALIASES)
    _require(cols, ("invoice_id", "customer_id", "invoice_date", "due_date", "amount"), source)

    invoices = []
    all_rows = ([first] if first is not None else []) + list(rows)
    for line_no, row in enumerate(all_rows, start=2):
        get = _getter(row, cols)
        try:
            amount = parse_amount(get("amount"))
            if amount is None:
                raise LedgerError("amount is blank")
            paid_date = parse_date(get("paid_date"))
            amount_paid = parse_amount(get("amount_paid"))
            if amount_paid is None:
                remaining = parse_amount(get("amount_remaining"))
                if remaining is not None:
                    amount_paid = amount - remaining
                else:
                    # No payment amount at all: a payment date means fully paid.
                    amount_paid = amount if paid_date else 0.0
            invoices.append(
                Invoice(
                    invoice_id=_text(get("invoice_id")),
                    customer_id=_text(get("customer_id")),
                    invoice_date=parse_date(get("invoice_date")),
                    due_date=parse_date(get("due_date")),
                    amount=amount,
                    amount_paid=amount_paid,
                    paid_date=paid_date,
                    disputed=_is_true(get("disputed")),
                )
            )
            if invoices[-1].invoice_date is None or invoices[-1].due_date is None:
                raise LedgerError("invoice_date and due_date are required")
        except LedgerError as exc:
            raise LedgerError(f"{source}:{line_no}: {exc}") from None
    return invoices


def rows_to_customers(rows: Iterable[Mapping[str, Any]], source: str = "customers", header: Optional[List[str]] = None) -> Dict[str, Customer]:
    rows = list(rows)
    if header is None:
        if not rows:
            return {}
        header = list(rows[0].keys())
    cols = _resolve_columns(header, CUSTOMER_ALIASES)
    _require(cols, ("customer_id",), source)
    customers = {}
    for line_no, row in enumerate(rows, start=2):
        get = _getter(row, cols)
        try:
            cid = _text(get("customer_id"))
            terms = parse_amount(get("payment_terms_days"))
            customers[cid] = Customer(
                customer_id=cid,
                name=_text(get("name")) or cid,
                credit_limit=parse_amount(get("credit_limit")) or 0.0,
                payment_terms_days=int(terms) if terms is not None else 30,
                industry=_text(get("industry")),
            )
        except LedgerError as exc:
            raise LedgerError(f"{source}:{line_no}: {exc}") from None
    return customers


def read_ledger(path: Path) -> List[Invoice]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        return rows_to_invoices(reader, str(path), header=reader.fieldnames or [])


def read_customers(path: Optional[Path]) -> Dict[str, Customer]:
    if path is None:
        return {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        return rows_to_customers(reader, str(path), header=reader.fieldnames or [])


def merge_customers(invoices: List[Invoice], customers: Dict[str, Customer]) -> Dict[str, Customer]:
    """Ensure every debtor in the ledger has a customer record."""
    merged = dict(customers)
    for inv in invoices:
        if inv.customer_id not in merged:
            merged[inv.customer_id] = Customer(customer_id=inv.customer_id, name=inv.customer_id)
    return merged
