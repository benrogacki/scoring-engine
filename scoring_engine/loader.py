"""Load and validate debtor ledger and customer master CSV files."""
from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .models import Customer, Invoice

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y")
TRUE_VALUES = {"1", "true", "yes", "y", "t"}

# Accept common alternative column headings from ERP exports.
LEDGER_ALIASES = {
    "invoice_id": ("invoice_id", "invoice", "invoice_no", "invoice_number", "document_no"),
    "customer_id": ("customer_id", "customer", "account", "account_code", "debtor_id"),
    "invoice_date": ("invoice_date", "document_date", "date"),
    "due_date": ("due_date", "due"),
    "amount": ("amount", "invoice_amount", "gross_amount", "total"),
    "amount_paid": ("amount_paid", "paid_amount", "paid"),
    "paid_date": ("paid_date", "payment_date", "cleared_date"),
    "disputed": ("disputed", "in_dispute", "dispute"),
}
CUSTOMER_ALIASES = {
    "customer_id": ("customer_id", "customer", "account", "account_code", "debtor_id"),
    "name": ("name", "customer_name", "account_name"),
    "credit_limit": ("credit_limit", "limit"),
    "payment_terms_days": ("payment_terms_days", "terms_days", "terms"),
    "industry": ("industry", "sector", "segment"),
}


class LedgerError(ValueError):
    """Raised when an input file cannot be interpreted."""


def parse_date(value: str) -> Optional[date]:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise LedgerError(f"Unrecognised date: {value!r}")


def parse_amount(value: str) -> Optional[float]:
    value = (value or "").strip()
    if not value:
        return None
    negative = value.startswith("(") and value.endswith(")")
    cleaned = re.sub(r"[^0-9.\-]", "", value)
    if cleaned in ("", "-", "."):
        raise LedgerError(f"Unrecognised amount: {value!r}")
    number = float(cleaned)
    return -number if negative else number


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


def read_ledger(path: Path) -> List[Invoice]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        cols = _resolve_columns(reader.fieldnames or [], LEDGER_ALIASES)
        _require(cols, ("invoice_id", "customer_id", "invoice_date", "due_date", "amount"), str(path))
        invoices = []
        for line_no, row in enumerate(reader, start=2):
            get = lambda key: row.get(cols[key], "") if key in cols else ""  # noqa: E731
            try:
                amount = parse_amount(get("amount"))
                if amount is None:
                    raise LedgerError("amount is blank")
                paid_date = parse_date(get("paid_date"))
                amount_paid = parse_amount(get("amount_paid"))
                if amount_paid is None:
                    # No explicit payment amount: a payment date means fully paid.
                    amount_paid = amount if paid_date else 0.0
                invoices.append(
                    Invoice(
                        invoice_id=get("invoice_id").strip(),
                        customer_id=get("customer_id").strip(),
                        invoice_date=parse_date(get("invoice_date")),
                        due_date=parse_date(get("due_date")),
                        amount=amount,
                        amount_paid=amount_paid,
                        paid_date=paid_date,
                        disputed=get("disputed").strip().lower() in TRUE_VALUES,
                    )
                )
            except LedgerError as exc:
                raise LedgerError(f"{path}:{line_no}: {exc}") from None
    return invoices


def read_customers(path: Optional[Path]) -> Dict[str, Customer]:
    if path is None:
        return {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        cols = _resolve_columns(reader.fieldnames or [], CUSTOMER_ALIASES)
        _require(cols, ("customer_id",), str(path))
        customers = {}
        for line_no, row in enumerate(reader, start=2):
            get = lambda key: row.get(cols[key], "") if key in cols else ""  # noqa: E731
            try:
                cid = get("customer_id").strip()
                terms = parse_amount(get("payment_terms_days"))
                customers[cid] = Customer(
                    customer_id=cid,
                    name=get("name").strip() or cid,
                    credit_limit=parse_amount(get("credit_limit")) or 0.0,
                    payment_terms_days=int(terms) if terms is not None else 30,
                    industry=get("industry").strip(),
                )
            except LedgerError as exc:
                raise LedgerError(f"{path}:{line_no}: {exc}") from None
    return customers


def merge_customers(invoices: List[Invoice], customers: Dict[str, Customer]) -> Dict[str, Customer]:
    """Ensure every debtor in the ledger has a customer record."""
    merged = dict(customers)
    for inv in invoices:
        if inv.customer_id not in merged:
            merged[inv.customer_id] = Customer(customer_id=inv.customer_id, name=inv.customer_id)
    return merged
