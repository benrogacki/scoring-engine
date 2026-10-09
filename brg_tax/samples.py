"""Synthetic sample clients (no real data). ``brg-tax sample --out clients/`` writes them.

Each client is built so particular rules fire; the expected figures are hand-worked in
tests/brg_tax/test_brg_golden.py. Names, companies and numbers are invented.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from .dates import add_months
from .ingest import CATEGORIES, load_mapping


@dataclass
class E:
    """One ledger posting in BRG terms; rendered into each package's export format."""
    d: date
    category: str
    desc: str
    net: Decimal
    vat: Decimal = Decimal("0")
    facts: Dict[str, Any] = field(default_factory=dict)
    contact: str = ""


def D(x: Any) -> Decimal:
    return Decimal(str(x))


def monthly(start: date, n: int, day: int, category: str, desc: str, net: Any, vat: Any = 0, facts=None, contact: str = "") -> List[E]:
    out = []
    for i in range(n):
        m = add_months(date(start.year, start.month, 1), i, month_end_rule=False)
        out.append(E(date(m.year, m.month, min(day, 28)), category, desc, D(net), D(vat), dict(facts or {}), contact))
    return out


def _code_for(mapping: Dict[str, Any], e: E) -> str:
    best = None
    for code, spec in mapping["codes"].items():
        if spec["category"] != e.category:
            continue
        dflt = spec.get("facts", {})
        if all(str(e.facts.get(k, v)) == str(v) for k, v in dflt.items()):
            if dflt and all(k in e.facts for k in dflt):
                return code
            best = best or code
    if best is None:
        raise KeyError(f"no {mapping['package']} code for category {e.category} {e.facts}")
    return best


def _facts_text(facts: Dict[str, Any], mapping_facts: Dict[str, Any]) -> str:
    extra = {k: v for k, v in facts.items() if mapping_facts.get(k) != v}
    return "; ".join(f"{k}={v}" for k, v in extra.items())


def _money(x: Decimal) -> str:
    return f"{x:.2f}"


def write_transactions(path: Path, package: str, entries: List[E]) -> None:
    m = load_mapping(package)
    cols = m["columns"]
    rows = []
    for i, e in enumerate(sorted(entries, key=lambda e: (e.d, e.category, e.desc)), start=1):
        code = _code_for(m, e)
        side = CATEGORIES[e.category]
        name = code if package == "quickbooks" else {
            "xero": XERO_NAMES, "freeagent": FA_NAMES}[package].get(code, e.category.replace("_", " ").title())
        facts = _facts_text(e.facts, m["codes"][code].get("facts", {}))
        if package == "xero":
            debit = e.net if side in ("expense", "asset") or e.category == "dividends" else Decimal(0)
            credit = e.net if debit == 0 else Decimal(0)
            rows.append({"Date": e.d.strftime("%d %b %Y"), "Source": "Spend Money" if debit else "Receive Money", "Description": e.desc,
                         "Reference": f"R{i:04d}", "Contact": e.contact, "Account Code": code, "Account": name,
                         "Debit": _money(debit) if debit else "", "Credit": _money(credit) if credit else "", "VAT": _money(e.vat), "BRG Facts": facts})
        elif package == "quickbooks":
            amount = e.net
            rows.append({"Date": e.d.strftime("%d/%m/%Y"), "Transaction Type": "Invoice" if side == "income" else "Expense", "No.": f"{i}",
                         "Name": e.contact, "Memo/Description": e.desc, "Account": code, "Amount": _money(amount),
                         "Tax Amount": _money(e.vat), "BRG Facts": facts})
        else:
            debit = e.net if side in ("expense", "asset") or e.category in ("drawings", "dividends") else Decimal(0)
            credit = e.net if debit == 0 else Decimal(0)
            rows.append({"Dated On": e.d.isoformat(), "Nominal Code": code, "Category": name, "Description": e.desc,
                         "Debit": _money(debit) if debit else "", "Credit": _money(credit) if credit else "", "VAT": _money(e.vat),
                         "Contact": e.contact, "Reference": f"FA{i:04d}", "BRG Facts": facts})
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


XERO_NAMES = {"200": "Sales", "310": "Cost of Goods Sold", "320": "Subcontractors", "400": "Advertising", "404": "Bank Fees",
              "412": "Consulting & Accounting", "416": "Depreciation", "420": "Entertainment", "421": "Staff Entertainment",
              "422": "Client Gifts", "429": "General Expenses", "433": "Insurance", "441": "Legal Expenses", "445": "Light, Power, Heating",
              "449": "Motor Vehicle Expenses", "450": "Car Lease", "456": "Fines and Penalties", "461": "Software", "465": "Research & Development",
              "469": "Rent", "473": "Repairs and Maintenance", "477": "Wages and Salaries", "478": "Directors' Remuneration",
              "479": "Employers National Insurance", "489": "Telephone & Internet", "711": "Plant and Machinery", "712": "Motor Vehicles",
              "713": "Buildings and Improvements", "720": "Computer Equipment", "710": "Office Equipment", "090": "Business Bank Account",
              "835": "Directors' Loan Account", "820": "VAT", "950": "Capital - Ordinary Shares", "960": "Retained Earnings",
              "970": "Dividends", "719": "Accumulated Depreciation", "714": "Vans"}
FA_NAMES = {"001": "Sales", "096": "Cost of Sales", "201": "Accountancy Fees", "202": "Legal and Professional", "250": "Advertising",
            "251": "Bank Charges", "253": "Entertaining", "260": "Insurance", "270": "Use of Home", "280": "Motor Expenses",
            "281": "Mileage Allowance", "286": "Travel", "350": "Training", "363": "Telephone", "365": "Computer Software",
            "402": "Directors Salaries", "403": "Employers NI", "450": "Depreciation", "602": "Computer Equipment",
            "750": "Business Account", "801": "Director's Loan Account", "817": "VAT", "901": "Drawings", "902": "Capital Introduced"}


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def build_tb(package: str, entries: List[E], start: date, end: date, extra: Dict[str, Decimal]) -> List[Dict[str, str]]:
    """Closing trial balance: P&L and asset additions from the period's postings, balance-sheet items from
    ``extra`` (code -> signed amount, debit positive); the bank is the balancing figure."""
    m = load_mapping(package)
    bal: Dict[str, Decimal] = {}
    for e in entries:
        if not (start <= e.d <= end):
            continue
        code = _code_for(m, e)
        side = CATEGORIES[e.category]
        signed = e.net if side in ("expense", "asset") or e.category in ("dividends", "drawings") else -e.net
        bal[code] = bal.get(code, Decimal(0)) + signed
    for code, v in extra.items():
        bal[code] = bal.get(code, Decimal(0)) + v
    bank = {"xero": "090", "quickbooks": "Current Account", "freeagent": "750"}[package]
    bal[bank] = bal.get(bank, Decimal(0)) - sum(bal.values())
    names = {"xero": XERO_NAMES, "freeagent": FA_NAMES}.get(package, {})
    rows = []
    for code in sorted(bal):
        v = bal[code]
        rows.append({"code": code, "name": names.get(code, code), "debit": _money(v) if v > 0 else "", "credit": _money(-v) if v < 0 else ""})
    return rows


def vat_returns(entries: List[E], quarters: List[tuple]) -> List[Dict[str, str]]:
    out = []
    for s, e in quarters:
        inside = [x for x in entries if s <= x.d <= e]
        b1 = sum((x.vat for x in inside if CATEGORIES[x.category] == "income"), Decimal(0))
        b4 = sum((x.vat for x in inside if CATEGORIES[x.category] != "income"), Decimal(0))
        b6 = sum((x.net for x in inside if CATEGORIES[x.category] == "income"), Decimal(0))
        b7 = sum((x.net for x in inside if CATEGORIES[x.category] in ("expense", "asset")), Decimal(0))
        out.append({"period_start": s.isoformat(), "period_end": e.isoformat(), "box1": _money(b1), "box4": _money(b4),
                    "box6": _money(b6), "box7": _money(b7)})
    return out


def quarters(first_end: date, n: int) -> List[tuple]:
    out = []
    for i in range(n):
        e = add_months(first_end, 3 * i)
        s = add_months(e, -3) + timedelta(days=1)
        out.append((s, e))
    return out


def _write_client(root: Path, profile: Dict[str, Any], entries: List[E], tb_extra: Dict[str, Decimal],
                  assets: Optional[List[Dict[str, Any]]] = None, dla: Optional[List[Dict[str, Any]]] = None,
                  vat_qs: Optional[List[tuple]] = None) -> Path:
    folder = root / profile["id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "profile.json").write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    write_transactions(folder / "transactions.csv", profile["package"], entries)
    per = profile["periods"][-1]
    s, e = date.fromisoformat(per["start"]), date.fromisoformat(per["end"])
    write_csv(folder / "trial_balance.csv", build_tb(profile["package"], entries, s, e, tb_extra))
    if assets:
        write_csv(folder / "assets.csv", assets)
    if dla:
        write_csv(folder / "dla.csv", dla)
    if vat_qs:
        write_csv(folder / "vat_returns.csv", vat_returns(entries, vat_qs))
    return folder


ASSET_COLS = ["id", "description", "date_acquired", "cost", "asset_class", "new_unused", "co2_gkm", "private_use_pct",
              "brought_into_use", "qualifying_cost", "disposal_date", "disposal_proceeds", "pool_bf", "claimed_fe", "txn_ref"]


def asset(**kw: Any) -> Dict[str, Any]:
    return {k: kw.get(k, "") for k in ASSET_COLS}


# --------------------------------------------------------------------------- the six clients
def c01() -> tuple:
    """Sole trader consultant approaching the VAT registration threshold (FreeAgent, not VAT registered)."""
    s = date(2025, 4, 1)
    en: List[E] = []
    en += monthly(s, 12, 28, "sales", "Consultancy fees", "6500.00", contact="Northwind Analytics Ltd")
    en += monthly(date(2026, 4, 1), 6, 28, "sales", "Consultancy fees", "7500.00", contact="Northwind Analytics Ltd")
    en += monthly(s, 12, 5, "software", "Cloud software subscriptions", "100.00")
    en += monthly(s, 12, 12, "telephone", "Mobile and broadband", "40.00", facts={"private_use_pct": 20})
    en += [
        E(date(2025, 6, 10), "insurance", "Professional indemnity insurance", D("600.00")),
        E(date(2026, 2, 20), "accountancy", "Accounts and tax return fee", D("900.00")),
        E(date(2026, 3, 31), "mileage", "Business mileage 2025-26 (own car)", D("900.00"), facts={"business_miles": 2000}),
        E(date(2025, 11, 14), "entertainment", "Client lunch - project kick-off", D("350.00"), facts={"attendees": "includes_non_employees"}),
        E(date(2025, 9, 18), "training", "Data visualisation refresher course", D("500.00"), facts={"new_skill": "no"}),
        E(date(2026, 3, 31), "use_of_home", "Use of home - simplified flat rate", D("312.00"), facts={"method": "flat_rate", "hours_per_month": 101}),
        E(date(2026, 3, 31), "depreciation", "Depreciation - computer equipment", D("500.00")),
        E(date(2025, 7, 8), "fixed_assets", "Laptop", D("1500.00"), facts={"asset_class": "computer"}),
    ]
    profile = {
        "id": "c01-asha-patel", "name": "Asha Patel Consulting", "entity_type": "sole_trader", "package": "freeagent", "region": "england",
        "periods": [{"start": "2025-04-01", "end": "2026-03-31"}],
        "vat": {"registered": False, "expected_next_30_days": 7800},
        "sole_trader": {"trading_start": "2019-05-01", "other_income": 0, "prior_year_liability": 15000, "poas_paid_for_year": 15000,
                        "turnover_by_tax_year": {"2024-25": 48000}, "mtd_software": False},
        "notes": "Synthetic. Exercises the VAT historic and forward-look tests, simplified expenses, mixed-use phone, entertaining and MTD forward look.",
    }
    assets = [asset(id="A1", description="Laptop", date_acquired="2025-07-08", cost="1500.00", asset_class="computer", new_unused="yes")]
    tb = {"902": D("-4000.00"), "901": D("30000.00")}
    return profile, en, tb, assets, None, None


def c02() -> tuple:
    """Small Ltd, single director, profits below the small profits limit, overdrawn DLA at year end (Xero)."""
    s = date(2025, 4, 1)
    en: List[E] = []
    en += monthly(s, 12, 25, "sales", "Design retainer", "6000.00", "1200.00", contact="Various clients")
    en += monthly(s, 12, 28, "directors_salary", "Director's salary", "1047.50")
    en += monthly(s, 12, 3, "software", "Design software licences", "200.00", "40.00")
    en += monthly(s, 12, 1, "rent", "Studio rent", "500.00")
    en += monthly(s, 12, 30, "bank_charges", "Bank charges", "10.00")
    en += [
        E(date(2026, 3, 31), "employer_nic", "Employer's NIC 2025-26", D("1135.50")),
        E(date(2026, 3, 20), "accountancy", "Year-end accounts", D("1800.00"), D("360.00")),
        E(date(2025, 12, 12), "staff_entertainment", "Christmas meal (director)", D("140.00"), D("28.00")),
        E(date(2025, 10, 9), "entertainment", "Client dinner - pitch", D("600.00"), facts={"attendees": "includes_non_employees"}),
        E(date(2025, 12, 1), "client_gifts", "Branded notebooks for 20 clients", D("240.00"), D("48.00"),
          facts={"carries_logo": "yes", "gift_type": "other", "cost_per_recipient": 12}),
        E(date(2025, 8, 4), "fines_penalties", "Parking penalty - company van bay", D("60.00"), facts={"fine_liability": "business"}),
        E(date(2026, 3, 31), "depreciation", "Depreciation", D("800.00")),
        E(date(2025, 7, 15), "fixed_assets", "Laptop (new)", D("2000.00"), D("400.00"), facts={"asset_class": "computer"}),
        E(date(2025, 9, 30), "dividends", "Interim dividend", D("10000.00")),
        E(date(2026, 3, 31), "dividends", "Interim dividend", D("10000.00")),
    ]
    profile = {
        "id": "c02-brightside", "name": "Brightside Design Ltd", "entity_type": "company", "package": "xero", "region": "england",
        "periods": [{"start": "2024-04-01", "end": "2025-03-31"}, {"start": "2025-04-01", "end": "2026-03-31"}],
        "incorporated": "2019-06-03", "company_number": "SC000002", "confirmation_statement_date": "2026-06-03",
        "associated_companies": 0,
        "people": [{"id": "d1", "name": "Jordan Hale", "shares": 100, "region": "england", "salary": 12570}],
        "vat": {"registered": True, "registration_date": "2021-01-01", "scheme": "standard", "stagger": "1",
                "frs_sector": "Advertising", "expected_next_12_months": 74000},
        "payroll": {"operates": True}, "opening_reserves": 15000, "dla_account_code": "835",
        "notes": "Synthetic. Single-director company: no Employment Allowance; overdrawn DLA with a repayment redrawn inside 30 days (s464C).",
    }
    dla = [
        {"date": "2025-06-30", "person_id": "d1", "description": "Personal card spend", "amount": "4000.00", "method": "bank"},
        {"date": "2025-09-30", "person_id": "d1", "description": "Personal transfer", "amount": "4000.00", "method": "bank"},
        {"date": "2026-01-15", "person_id": "d1", "description": "Personal transfer", "amount": "4000.00", "method": "bank"},
        {"date": "2026-02-28", "person_id": "d1", "description": "Repayment", "amount": "-3000.00", "method": "bank"},
        {"date": "2026-04-20", "person_id": "d1", "description": "Repayment from personal account", "amount": "-6000.00", "method": "bank"},
        {"date": "2026-05-10", "person_id": "d1", "description": "Personal transfer", "amount": "6000.00", "method": "bank"},
    ]
    assets = [asset(id="A1", description="Laptop (new)", date_acquired="2025-07-15", cost="2000.00", asset_class="computer", new_unused="yes")]
    tb = {"835": D("9000.00"), "960": D("-15000.00"), "950": D("-100.00"), "719": D("-800.00")}
    return profile, en, tb, assets, dla, quarters(date(2025, 6, 30), 4)


def c03() -> tuple:
    """Ltd in the marginal relief band, one associated company, short period straddling 1 April (QuickBooks)."""
    s = date(2025, 10, 1)
    en: List[E] = []
    en += monthly(s, 9, 26, "sales", "Machined components", "20000.00", "4000.00", contact="Trade customers")
    en += monthly(s, 9, 10, "cost_of_sales", "Steel and consumables", "7000.00", "1400.00")
    en += monthly(s, 9, 28, "directors_salary", "Directors' salaries (2)", "2095.00")
    en += monthly(s, 9, 1, "rent", "Unit rent", "2500.00")
    en += monthly(s, 9, 15, "light_heat", "Electricity", "600.00", "120.00")
    en += monthly(s, 9, 30, "bank_charges", "Bank charges", "45.00")
    en += monthly(s, 9, 18, "telephone", "Telephone", "100.00", "20.00")
    en += [
        E(date(2025, 10, 3), "insurance", "Employers' and public liability", D("3000.00")),
        E(date(2026, 6, 25), "accountancy", "Accounts - short period", D("2400.00"), D("480.00")),
        E(date(2026, 2, 11), "repairs", "Lathe spindle repair", D("1800.00"), D("360.00"), facts={"improvement": "no"}),
        E(date(2026, 6, 30), "depreciation", "Depreciation", D("4000.00")),
        E(date(2026, 3, 5), "advertising", "Trade directory listing", D("240.00"), D("48.00")),
        E(date(2025, 11, 20), "fixed_assets", "Used lathe", D("1500.00"), D("300.00"), facts={"asset_class": "plant"}),
        E(date(2026, 3, 20), "dividends", "Dividend", D("20000.00")),
    ]
    profile = {
        "id": "c03-northgate", "name": "Northgate Engineering Ltd", "entity_type": "company", "package": "quickbooks", "region": "england",
        "periods": [{"start": "2024-10-01", "end": "2025-09-30"}, {"start": "2025-10-01", "end": "2026-06-30"}],
        "incorporated": "2016-09-12", "company_number": "00000003", "confirmation_statement_date": "2026-09-12",
        "associated_companies": 1, "associated_basis": "control",
        "people": [{"id": "d1", "name": "Priya Shah", "shares": 50, "salary": 12570}, {"id": "d2", "name": "Marcus Shah", "shares": 50, "salary": 12570}],
        "vat": {"registered": True, "registration_date": "2017-01-01", "scheme": "standard", "stagger": "1"},
        "payroll": {"operates": True}, "opening_reserves": 80000,
        "notes": "Synthetic. Accounting date changed to 30 June: 9-month period, limits halved for one associated company and reduced by 273/365, split across FY2025 and FY2026.",
    }
    assets = [asset(id="A1", description="Used lathe", date_acquired="2025-11-20", cost="1500.00", asset_class="plant", new_unused="no")]
    tb = {"Retained Earnings": D("-80000.00")}
    return profile, en, tb, assets, None, quarters(date(2025, 12, 31), 3)


def c04() -> tuple:
    """Ltd with significant capex: new plant, used plant, a car, an integral feature and a building extension (Xero)."""
    s = date(2025, 4, 1)
    en: List[E] = []
    en += monthly(s, 12, 26, "sales", "Joinery contracts", "75000.00", "15000.00", contact="Contract customers")
    en += monthly(s, 12, 10, "cost_of_sales", "Timber and hardware", "22000.00", "4400.00")
    en += monthly(s, 12, 28, "wages", "Staff wages", "10000.00")
    en += monthly(s, 12, 28, "directors_salary", "Director's salary", "1047.50")
    en += monthly(s, 12, 1, "rent", "Workshop rent", "4000.00")
    en += monthly(s, 12, 15, "light_heat", "Electricity and gas", "1500.00", "300.00")
    en += monthly(s, 12, 5, "car_lease", "Car lease - estate car", "450.00", "90.00", facts={"co2_gkm": 120})
    en += monthly(s, 12, 30, "bank_charges", "Bank charges", "50.00")
    en += monthly(s, 12, 18, "telephone", "Telephone", "150.00", "30.00")
    en += [
        E(date(2026, 3, 31), "employer_nic", "Employer's NIC net of Employment Allowance", D("6385.50")),
        E(date(2025, 6, 2), "insurance", "Business insurance", D("9600.00")),
        E(date(2025, 11, 3), "motor_expenses", "Van fuel and servicing", D("6000.00"), D("1000.00")),
        E(date(2025, 9, 22), "legal_professional", "Planning and building-contract legal fees - extension", D("5000.00"), D("1000.00"), facts={"fee_nature": "capital"}),
        E(date(2026, 3, 18), "accountancy", "Accounts and corporation tax", D("4200.00"), D("840.00")),
        E(date(2026, 1, 9), "repairs", "Roof repairs - like for like", D("7000.00"), D("1400.00"), facts={"improvement": "no"}),
        E(date(2026, 3, 31), "depreciation", "Depreciation", D("45000.00")),
        E(date(2025, 10, 6), "advertising", "Trade show stand", D("3000.00"), D("600.00")),
        E(date(2026, 2, 16), "research_development", "Prototype jig development materials", D("3500.00"), D("700.00")),
        E(date(2025, 6, 12), "fixed_assets", "CNC router (new)", D("120000.00"), D("24000.00"), facts={"asset_class": "plant"}),
        E(date(2025, 8, 19), "fixed_assets", "Forklift (used)", D("18000.00"), D("3600.00"), facts={"asset_class": "plant"}),
        E(date(2025, 9, 8), "fixed_assets", "Workshop electrical installation", D("10000.00"), D("2000.00"), facts={"asset_class": "plant"}),
        E(date(2025, 7, 1), "fixed_assets", "Company car (95g/km)", D("32000.00"), facts={"asset_class": "car"}),
        E(date(2025, 9, 30), "fixed_assets", "Workshop extension", D("200000.00"), D("40000.00"), facts={"asset_class": "building"}),
        E(date(2025, 9, 30), "dividends", "Interim dividend", D("50000.00")),
        E(date(2026, 3, 31), "dividends", "Final dividend", D("50000.00")),
    ]
    profile = {
        "id": "c04-ridgeway", "name": "Ridgeway Joinery Ltd", "entity_type": "company", "package": "xero", "region": "england",
        "periods": [{"start": "2024-04-01", "end": "2025-03-31"}, {"start": "2025-04-01", "end": "2026-03-31"}],
        "incorporated": "2012-02-14", "company_number": "00000004", "confirmation_statement_date": "2026-02-14",
        "associated_companies": 0,
        "people": [{"id": "d1", "name": "Sam Okafor", "shares": 100, "salary": 12570},
                   {"id": "p2", "name": "Alex Okafor", "is_director": False, "shares": 50, "share_class": "B", "works_in_business": False,
                    "connected_to": "d1"}],
        "vat": {"registered": True, "registration_date": "2012-04-01", "scheme": "standard", "stagger": "1"},
        "payroll": {"operates": True, "other_employees_above_st": 3, "other_employer_nic": 15750},
        "opening_reserves": 400000, "pools_bf": {"main": 40000, "special": 0},
        "notes": "Synthetic. Capital expenditure across every allowance type; car lease VAT over-claimed in the books; spouse holds B shares (settlements screen).",
    }
    assets = [
        asset(id="A1", description="CNC router (new)", date_acquired="2025-06-12", cost="120000.00", asset_class="plant", new_unused="yes"),
        asset(id="A2", description="Forklift (used)", date_acquired="2025-08-19", cost="18000.00", asset_class="plant", new_unused="no"),
        asset(id="A3", description="Workshop electrical installation", date_acquired="2025-09-08", cost="10000.00", asset_class="integral_feature", new_unused="yes"),
        asset(id="A4", description="Company car (95g/km)", date_acquired="2025-07-01", cost="32000.00", asset_class="car", new_unused="yes", co2_gkm=95),
        asset(id="A5", description="Workshop extension", date_acquired="2025-09-30", cost="200000.00", asset_class="building",
              brought_into_use="2025-10-01", qualifying_cost="200000.00"),
        asset(id="A0", description="Old van", date_acquired="2019-05-01", cost="15000.00", asset_class="van", new_unused="no",
              disposal_date="2025-11-15", disposal_proceeds="3000.00", pool_bf="yes"),
    ]
    tb = {"960": D("-400000.00"), "950": D("-150.00"), "719": D("-45000.00")}
    return profile, en, tb, assets, None, quarters(date(2025, 6, 30), 4)


def c05() -> tuple:
    """IT contractor Ltd: IR35 status question and a use-of-home claim, Scottish director (FreeAgent)."""
    s = date(2025, 7, 1)
    en: List[E] = []
    en += monthly(s, 12, 27, "sales", "Contract day rates", "9000.00", "1800.00", contact="Stackline Recruitment Ltd")
    en += monthly(s, 12, 28, "directors_salary", "Director's salary", "1047.50")
    en += monthly(s, 12, 4, "software", "Developer tools", "50.00", "10.00")
    en += monthly(s, 12, 20, "travel", "Rail fares to client site", "200.00", facts={"temporary_workplace": "yes"})
    en += [
        E(date(2026, 6, 15), "sales", "Overtime days", D("2000.00"), D("400.00"), contact="Stackline Recruitment Ltd"),
        E(date(2026, 6, 30), "employer_nic", "Employer's NIC 2025-26", D("1135.50")),
        E(date(2026, 6, 20), "accountancy", "Accounts and CT600", D("1500.00"), D("300.00")),
        E(date(2025, 7, 2), "insurance", "Professional indemnity insurance", D("500.00")),
        E(date(2026, 6, 30), "use_of_home", "Use of home office - payment to director", D("1200.00")),
        E(date(2026, 6, 30), "depreciation", "Depreciation", D("600.00")),
        E(date(2025, 7, 10), "fixed_assets", "Laptop (new)", D("1800.00"), D("360.00"), facts={"asset_class": "computer"}),
        E(date(2025, 12, 19), "dividends", "Interim dividend", D("30000.00")),
        E(date(2026, 6, 26), "dividends", "Interim dividend", D("30000.00")),
    ]
    profile = {
        "id": "c05-kestrel", "name": "Kestrel Data Ltd", "entity_type": "company", "package": "freeagent", "region": "scotland",
        "periods": [{"start": "2024-07-01", "end": "2025-06-30"}, {"start": "2025-07-01", "end": "2026-06-30"}],
        "incorporated": "2020-06-22", "company_number": "SC000005", "confirmation_statement_date": "2026-06-22",
        "associated_companies": 0,
        "people": [{"id": "d1", "name": "Morven Reid", "shares": 100, "region": "scotland", "salary": 12570}],
        "contracts": [{"end_client": "Halden Bank plc (via Stackline Recruitment)", "client_size": "unknown", "sds": "none", "via_agency": True}],
        "vat": {"registered": True, "registration_date": "2020-09-01", "scheme": "standard", "stagger": "3",
                "frs_sector": "Computer and IT consultancy or data processing"},
        "payroll": {"operates": True}, "opening_reserves": 30000,
        "notes": "Synthetic. Single IT contract via an agency with no status determination; actual-cost use of home payments; Scottish taxpayer.",
    }
    assets = [asset(id="A1", description="Laptop (new)", date_acquired="2025-07-10", cost="1800.00", asset_class="computer", new_unused="yes")]
    tb = {}
    return profile, en, tb, assets, None, quarters(date(2025, 8, 31), 4)


def c06() -> tuple:
    """Sole trader (Wales) at a profit level where incorporation is worth comparing, within MTD for Income Tax (QuickBooks)."""
    s = date(2025, 4, 1)
    en: List[E] = []
    en += monthly(s, 12, 26, "sales", "Plumbing and heating jobs", "12500.00", "2500.00", contact="Domestic customers")
    en += monthly(s, 12, 9, "cost_of_sales", "Plumbing materials", "3750.00", "750.00")
    en += monthly(s, 12, 22, "subcontractors", "Subcontract labour", "1000.00")
    en += monthly(s, 12, 14, "telephone", "Mobile phone", "50.00", facts={"private_use_pct": 25})
    en += monthly(s, 12, 30, "drawings", "Drawings", "3000.00")
    en += [E(date(2025, 4 + 3 * i, 15), "motor_expenses", "Van fuel, insurance and servicing", D("1000.00"), facts={"private_use_pct": 10}) for i in range(3)]
    en += [
        E(date(2026, 1, 15), "motor_expenses", "Van fuel, insurance and servicing", D("1000.00"), facts={"private_use_pct": 10}),
        E(date(2025, 5, 2), "insurance", "Public liability insurance", D("1800.00")),
        E(date(2026, 3, 10), "accountancy", "Accounts and tax return", D("1200.00"), D("240.00")),
        E(date(2025, 9, 5), "advertising", "Van livery and flyers", D("1000.00"), D("200.00")),
        E(date(2026, 3, 31), "depreciation", "Depreciation - van", D("2800.00")),
        E(date(2025, 12, 5), "entertainment", "Supplier Christmas drinks", D("200.00"), facts={"attendees": "includes_non_employees"}),
        E(date(2025, 8, 21), "fines_penalties", "Speeding fine", D("100.00"), facts={"fine_liability": "business"}),
        E(date(2026, 3, 31), "use_of_home", "Use of home - simplified flat rate", D("120.00"), facts={"method": "flat_rate", "hours_per_month": 30}),
        E(date(2025, 6, 18), "fixed_assets", "Used van", D("14000.00"), D("2800.00"), facts={"asset_class": "van"}),
    ]
    profile = {
        "id": "c06-hargreaves", "name": "Tom Hargreaves Plumbing & Heating", "entity_type": "sole_trader", "package": "quickbooks", "region": "wales",
        "periods": [{"start": "2025-04-01", "end": "2026-03-31"}],
        "vat": {"registered": True, "registration_date": "2016-07-01", "scheme": "standard", "stagger": "1",
                "frs_sector": "General building or construction services"},
        "sole_trader": {"trading_start": "2014-04-01", "other_income": 0, "prior_year_liability": 16000, "poas_paid_for_year": 16000,
                        "turnover_by_tax_year": {"2024-25": 138000}, "mtd_software": False},
        "notes": "Synthetic. Welsh taxpayer; van with private use in a single-asset pool; MTD for Income Tax mandated from 2026-27; FRS comparison.",
    }
    assets = [asset(id="A1", description="Used van", date_acquired="2025-06-18", cost="14000.00", asset_class="van", new_unused="no", private_use_pct=10)]
    tb = {}
    return profile, en, tb, assets, None, quarters(date(2025, 6, 30), 4)


CLIENTS = [c01, c02, c03, c04, c05, c06]


def generate(out: Path) -> List[Path]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    folders = []
    for build in CLIENTS:
        profile, en, tb, assets, dla, qs = build()
        folders.append(_write_client(out, profile, en, tb, assets, dla, qs))
    return folders
