"""Read a client folder: profile, bookkeeping export, fixed asset register, DLA, VAT returns, TB.

Bookkeeping exports differ by package. ``ingest/mappings/<package>.json`` names the columns and maps
each nominal code (or account name, for QuickBooks) to a BRG category, with optional default facts.
A ``BRG Facts`` column on the export carries reviewer-added facts as ``key=value; key=value``.
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..models import Asset, Client, ClientData, DLAEntry, TBLine, Transaction, VatReturn
from ..money import to_pence

MAPPINGS_DIR = Path(__file__).parent / "mappings"

# category -> side of the ledger. Income/expense categories form the profit and loss account.
CATEGORIES: Dict[str, str] = {
    # income
    "sales": "income", "other_income": "income", "interest_received": "income",
    # expenses
    "cost_of_sales": "expense", "subcontractors": "expense", "wages": "expense", "directors_salary": "expense",
    "employer_nic": "expense", "staff_pension": "expense", "director_pension": "expense", "rent": "expense",
    "rates": "expense", "light_heat": "expense", "use_of_home": "expense", "motor_expenses": "expense",
    "car_lease": "expense", "mileage": "expense", "travel": "expense", "subsistence": "expense",
    "entertainment": "expense", "staff_entertainment": "expense", "client_gifts": "expense", "staff_gifts": "expense",
    "telephone": "expense", "software": "expense", "repairs": "expense", "legal_professional": "expense",
    "accountancy": "expense", "insurance": "expense", "bank_charges": "expense", "loan_interest": "expense",
    "fines_penalties": "expense", "depreciation": "expense", "subscriptions": "expense", "training": "expense",
    "advertising": "expense", "donations": "expense", "research_development": "expense", "sundry": "expense",
    "corporation_tax": "expense",
    # balance sheet
    "fixed_assets": "asset", "bank": "asset", "debtors": "asset", "dla": "asset", "drawings": "equity",
    "vat_control": "liability", "paye_control": "liability", "creditors": "liability", "ct_liability": "liability",
    "share_capital": "equity", "reserves": "equity", "dividends": "equity", "capital_account": "equity",
    "accumulated_depreciation": "asset",
    "uncategorised": "expense",
}
PL_SIDES = ("income", "expense")


class IngestError(ValueError):
    pass


def load_mapping(package: str, directory: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(directory or MAPPINGS_DIR) / f"{package}.json"
    if not p.exists():
        raise IngestError(f"no nominal-code mapping for package {package!r} ({p})")
    m = json.loads(p.read_text(encoding="utf-8"))
    for code, spec in m["codes"].items():
        if spec["category"] not in CATEGORIES:
            raise IngestError(f"{p.name}: code {code} maps to unknown category {spec['category']!r}")
    return m


def parse_date(text: str, formats: List[str]) -> date:
    text = (text or "").strip()
    for f in formats + ["%Y-%m-%d"]:
        try:
            return datetime.strptime(text, f).date()
        except ValueError:
            continue
    raise IngestError(f"unrecognised date {text!r}")


def _coerce(v: str) -> Any:
    v = v.strip()
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def parse_facts(text: str) -> Dict[str, Any]:
    facts: Dict[str, Any] = {}
    for part in (text or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            facts[k.strip()] = _coerce(v)
    return facts


def _rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return [{(k or "").strip(): (v or "") for k, v in row.items()} for row in csv.DictReader(fh)]


def read_transactions(path: Path, mapping: Dict[str, Any]) -> Tuple[List[Transaction], List[Dict[str, Any]]]:
    cols = mapping["columns"]
    fmts = mapping.get("date_formats", [])
    txns, unmapped = [], []
    for i, row in enumerate(_rows(path), start=2):
        code = row.get(cols["code"], "").strip()
        spec = mapping["codes"].get(code)
        if mapping.get("amount_mode") == "debit_credit":
            raw = to_pence(row.get(cols["debit"]) or 0) - to_pence(row.get(cols["credit"]) or 0)
        else:
            raw = to_pence(row.get(cols["amount"]) or 0)
        vat = abs(to_pence(row.get(cols.get("vat", ""), "") or 0))
        if spec is None:
            category, side, facts = "uncategorised", "expense", {}
            unmapped.append({"row": i, "code": code, "account": row.get(cols.get("account", ""), ""), "description": row.get(cols["description"], "")})
        else:
            category = spec["category"]
            side = CATEGORIES[category]
            facts = dict(spec.get("facts", {}))
        if mapping.get("amount_mode") == "debit_credit":
            net = -raw if side in ("income", "liability", "equity") else raw
        else:
            net = raw
        if net < 0:
            vat = -vat
        facts.update(parse_facts(row.get(cols.get("facts", "BRG Facts"), "")))
        if "category" in facts:            # reviewer recode via BRG Facts
            category = str(facts.pop("category"))
            if category not in CATEGORIES:
                raise IngestError(f"{path.name} row {i}: unknown category {category!r}")
            side = CATEGORIES[category]
        txns.append(Transaction(
            id=f"{path.stem}:{i}", date=parse_date(row.get(cols["date"], ""), fmts), code=code,
            account=row.get(cols.get("account", ""), ""), description=row.get(cols["description"], ""),
            contact=row.get(cols.get("contact", ""), ""), net=net, vat=vat, category=category, side=side,
            facts=facts, source=f"{path.name}:{i}",
        ))
    return txns, unmapped


def read_assets(path: Path) -> List[Asset]:
    out = []
    for row in _rows(path):
        d = {k: (v.strip() or None) for k, v in row.items() if k}
        for b in ("new_unused", "pool_bf", "claimed_fe"):
            if d.get(b) is not None:
                d[b] = d[b].lower() in ("y", "yes", "true", "1")
        for n in ("co2_gkm", "private_use_pct"):
            if d.get(n) is not None:
                d[n] = int(d[n])
        if d.get("private_use_pct") is None:
            d.pop("private_use_pct", None)
        for k in ("pool_bf", "claimed_fe"):
            if d.get(k) is None:
                d.pop(k, None)
        d["txn_ref"] = d.get("txn_ref") or ""
        out.append(Asset(**d))
    return out


def read_dla(path: Path) -> List[DLAEntry]:
    return [DLAEntry(date=date.fromisoformat(r["date"]), person_id=r["person_id"], description=r.get("description", ""),
                     amount=to_pence(r["amount"]), method=(r.get("method") or "bank").strip()) for r in _rows(path)]


def read_vat_returns(path: Path) -> List[VatReturn]:
    return [VatReturn(period_start=date.fromisoformat(r["period_start"]), period_end=date.fromisoformat(r["period_end"]),
                      box1=to_pence(r["box1"]), box4=to_pence(r["box4"]), box6=to_pence(r.get("box6") or 0),
                      box7=to_pence(r.get("box7") or 0)) for r in _rows(path)]


def read_tb(path: Path) -> List[TBLine]:
    return [TBLine(code=r["code"], name=r.get("name", ""), debit=to_pence(r.get("debit") or 0), credit=to_pence(r.get("credit") or 0))
            for r in _rows(path)]


def load_client(folder: Path, mappings_dir: Optional[Path] = None) -> ClientData:
    folder = Path(folder)
    profile = folder / "profile.json"
    if not profile.exists():
        raise IngestError(f"{folder}: profile.json not found")
    client = Client(**json.loads(profile.read_text(encoding="utf-8")))
    mapping = load_mapping(client.package, mappings_dir)
    txns, unmapped = read_transactions(folder / "transactions.csv", mapping) if (folder / "transactions.csv").exists() else ([], [])
    return ClientData(
        client=client, transactions=txns, unmapped=unmapped,
        assets=read_assets(folder / "assets.csv") if (folder / "assets.csv").exists() else [],
        dla=read_dla(folder / "dla.csv") if (folder / "dla.csv").exists() else [],
        vat_returns=read_vat_returns(folder / "vat_returns.csv") if (folder / "vat_returns.csv").exists() else [],
        trial_balance=read_tb(folder / "trial_balance.csv") if (folder / "trial_balance.csv").exists() else [],
        source_dir=str(folder),
    )


def load_clients(root: Path) -> List[ClientData]:
    root = Path(root)
    folders = sorted(p for p in root.iterdir() if p.is_dir() and (p / "profile.json").exists())
    if not folders:
        raise IngestError(f"no client folders (with profile.json) under {root}")
    return [load_client(p) for p in folders]
