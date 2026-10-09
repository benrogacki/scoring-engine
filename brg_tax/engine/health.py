"""Data health checks run before any figure is trusted.

A failed check marks the client's results "not trusted" in every output; warnings are shown alongside.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Set

from ..dates import fy_label_to_params_label, fy_of, tax_year_of, tax_years_spanned, fy_slices
from ..ingest import CATEGORIES, load_mapping
from ..models import ClientData
from ..money import fmt
from ..params import ParamStore

TOLERANCE = 100   # £1.00 in pence: differences up to this are rounding


def _check(cid: str, name: str, status: str, detail: str, **extra: Any) -> Dict[str, Any]:
    return {"id": cid, "name": name, "status": status, "detail": detail, **extra}


def years_in_use(data: ClientData, as_of: date) -> List[str]:
    c = data.client
    labels: Set[str] = set()
    for p in c.periods[-1:]:
        labels.update(tax_years_spanned(p.start, p.end))
        labels.update(fy_label_to_params_label(fy) for fy, *_ in fy_slices(p.start, p.end))
    labels.add(tax_year_of(as_of))
    labels.add(fy_label_to_params_label(fy_of(as_of)))
    return sorted(labels)


def run_checks(data: ClientData, store: ParamStore, as_of: date) -> Dict[str, Any]:
    c = data.client
    per = c.period
    checks: List[Dict[str, Any]] = []
    mapping = load_mapping(c.package)
    code_cat = {code: spec["category"] for code, spec in mapping["codes"].items()}

    # 1 trial balance balances
    if data.trial_balance:
        dr = sum(l.debit for l in data.trial_balance)
        cr = sum(l.credit for l in data.trial_balance)
        checks.append(_check("tb_balances", "Trial balance balances", "ok" if abs(dr - cr) <= TOLERANCE else "fail",
                             f"Debits {fmt(dr)}, credits {fmt(cr)}" + ("" if abs(dr - cr) <= TOLERANCE else f", difference {fmt(dr - cr)}")))
        # 2 ledger agrees to TB profit
        tb_profit = 0
        unknown = []
        for l in data.trial_balance:
            cat = code_cat.get(l.code)
            if cat is None:
                unknown.append(l.code)
                continue
            if CATEGORIES[cat] in ("income", "expense"):
                tb_profit += l.credit - l.debit
        pl = [t for t in data.transactions if per.start <= t.date <= per.end and t.side in ("income", "expense")]
        ledger_profit = sum(t.net for t in pl if t.side == "income") - sum(t.net for t in pl if t.side == "expense")
        diff = tb_profit - ledger_profit
        checks.append(_check("ledger_agrees_tb", "Ledger profit agrees to the trial balance", "ok" if abs(diff) <= TOLERANCE else "fail",
                             f"TB profit {fmt(tb_profit)}, ledger {fmt(ledger_profit)}" + (f", difference {fmt(diff)}" if abs(diff) > TOLERANCE else "")
                             + (f"; TB codes not in the mapping: {', '.join(unknown)}" if unknown else "")))
    else:
        checks.append(_check("tb_balances", "Trial balance balances", "fail", "No trial_balance.csv supplied"))

    # 3 categorised
    n = len(data.unmapped)
    checks.append(_check("categorised", "No uncategorised transactions", "ok" if n == 0 else "fail",
                         "All transactions map to a BRG category" if n == 0 else
                         f"{n} transaction(s) with codes not in the {c.package} mapping: " + ", ".join(sorted({u['code'] for u in data.unmapped}))))

    # 4 fixed asset register agrees to ledger additions
    far = sum(a.cost for a in data.assets if not a.pool_bf and per.start <= a.date_acquired <= per.end)
    ledger_fa = sum(t.net for t in data.transactions if t.category == "fixed_assets" and per.start <= t.date <= per.end)
    status = "ok" if abs(far - ledger_fa) <= TOLERANCE else "fail"
    checks.append(_check("far_agrees", "Fixed asset register agrees to the ledger", status,
                         f"Register additions {fmt(far)}, ledger fixed asset postings {fmt(ledger_fa)}" + ("" if status == "ok" else f", difference {fmt(far - ledger_fa)}")))

    # 5 DLA reconciles
    if c.entity_type == "company":
        tb_dla = [l for l in data.trial_balance if code_cat.get(l.code) == "dla"]
        dla_bal = sum(e.amount for e in data.dla if e.date <= per.end)
        if tb_dla:
            tb_bal = sum(l.debit - l.credit for l in tb_dla)
            ok = abs(tb_bal - dla_bal) <= TOLERANCE
            checks.append(_check("dla_reconciles", "Director's loan account reconciles", "ok" if ok else "fail",
                                 f"DLA schedule {fmt(dla_bal)} (positive = owed by the director), TB {fmt(tb_bal)}" + ("" if ok else f", difference {fmt(tb_bal - dla_bal)}")))
        else:
            checks.append(_check("dla_reconciles", "Director's loan account reconciles", "warn" if data.dla else "ok",
                                 "No DLA account in the trial balance" + (" but a DLA schedule was supplied" if data.dla else "")))

    # 6 VAT returns agree to ledger
    if c.vat.registered:
        rets = [r for r in data.vat_returns if r.period_end >= per.start and r.period_start <= per.end]
        if not rets:
            checks.append(_check("vat_returns_agree", "VAT returns agree to the ledger", "warn", "No VAT returns supplied for the period"))
        else:
            s, e = min(r.period_start for r in rets), max(r.period_end for r in rets)
            inside = [t for t in data.transactions if s <= t.date <= e]
            out_v = sum(t.vat for t in inside if t.side == "income")
            in_v = sum(t.vat for t in inside if t.side != "income")
            b1, b4 = sum(r.box1 for r in rets), sum(r.box4 for r in rets)
            ok = abs(out_v - b1) <= TOLERANCE and abs(in_v - b4) <= TOLERANCE
            checks.append(_check("vat_returns_agree", "VAT returns agree to the ledger", "ok" if ok else "fail",
                                 f"{len(rets)} return(s) {s.isoformat()} to {e.isoformat()}: box 1 {fmt(b1)} vs ledger output VAT {fmt(out_v)}; "
                                 f"box 4 {fmt(b4)} vs ledger input VAT {fmt(in_v)}"))

    # 7 parameters exist and are verified for every year spanned
    labels = years_in_use(data, as_of)
    missing = [y for y in labels if y not in store.files]
    unverified = sum(1 for y in labels if y in store.files for e in store.files[y].params.values() if not e.get("verified"))
    total = sum(len(store.files[y].params) for y in labels if y in store.files)
    if missing:
        checks.append(_check("params", "Parameters exist and are verified", "fail", f"No parameter file for {', '.join(missing)}"))
    else:
        checks.append(_check("params", "Parameters exist and are verified", "warn" if unverified else "ok",
                             f"Years {', '.join(labels)}: {total - unverified} of {total} values verified against GOV.UK"
                             + (" - run `brg-tax params-update`" if unverified else ""), years=labels, unverified=unverified))

    # 8 associated companies recorded
    if c.entity_type == "company":
        ok = c.associated_companies is not None
        checks.append(_check("associated", "Associated-company information present", "ok" if ok else "fail",
                             f"{c.associated_companies} associated compan{'y' if c.associated_companies == 1 else 'ies'} recorded"
                             + (" (basis uncertain - in review queue)" if c.associated_basis == "uncertain" else "") if ok else
                             "associated_companies is not set in profile.json - CT limits cannot be determined"))
        if not c.people or not sum(p.shares for p in c.people):
            checks.append(_check("shareholders", "Directors and shareholdings recorded", "warn", "No shareholdings recorded - the extraction optimiser cannot split dividends"))

    worst = "fail" if any(k["status"] == "fail" for k in checks) else ("warn" if any(k["status"] == "warn" for k in checks) else "ok")
    return {"status": worst, "checks": checks, "years": labels}
