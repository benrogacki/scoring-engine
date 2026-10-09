"""Self-employment: tax-adjusted profit, income tax, Class 2/4 NIC, payments on account, MTD for
Income Tax readiness, and the sole trader vs limited company comparator."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List

from ..dates import days_incl, tax_year_bounds, tax_year_of, twelve_months_from
from ..models import ClientData, Line, Treatment
from ..money import at_rate, bp, fmt, muldiv, to_pence
from . import taxmath
from .capital_allowances import CAResult
from .context import Ctx
from .ct import ct_schedule
from .extraction import region_bands, ty_model

USES_RULES = ["SA-PROFIT-01", "SA-BASIS-01", "SA-BASIS-02", "SA-IT-01", "SA-C4-01", "SA-C2-01", "SA-POA-01", "SA-POA-02",
              "SA-MTD-01", "SA-SIMP-01", "SA-TA-01", "SA-BADGES-01", "SA-INC-01", "EXT-IT-SCO-01", "EXT-IT-WAL-01", "EXT-PA-01",
              "INC-INT-02"]


@dataclass
class SAResult:
    tax_year: str = ""
    lines: List[Line] = field(default_factory=list)
    accounting_profit: int = 0
    taxable_profit: int = 0
    income_tax: int = 0
    class4: int = 0
    class2: int = 0
    class2_status: str = ""
    total: int = 0
    poa_next: int = 0
    balancing: int = 0
    it_detail: Dict[str, Any] = field(default_factory=dict)
    mtd: Dict[str, Any] = field(default_factory=dict)
    comparator: Dict[str, Any] = field(default_factory=dict)
    comparator_model: Dict[str, Any] = field(default_factory=dict)
    provisional: bool = False


def compute(ctx: Ctx, data: ClientData, treatments: List[Treatment], ca: CAResult) -> SAResult:
    c = ctx.client
    st = c.sole_trader
    per = c.period
    res = SAResult()
    rule = lambda rid: ctx.rule(rid, per.end)   # noqa: E731

    def auth(rids: List[str]) -> List[str]:
        out: List[str] = []
        for rid in rids:
            for a in rule(rid).authority:
                if a not in out:
                    out.append(a)
        return out

    def add(key: str, label: str, amount: int, rids: List[str], kind: str = "line", **kw: Any) -> Line:
        ln = Line(key=key, label=label, amount=amount, kind=kind, rules=rids, authority=auth(rids), **kw)
        res.lines.append(ln)
        return ln

    # ---- basis period: tax year basis; an accounting date of 31 March to 4 April is treated as 5 April
    aligned = per.end.month == 3 and per.end.day == 31 or (per.end.month == 4 and per.end.day <= 5)
    label = tax_year_of(per.end + timedelta(days=5)) if aligned else tax_year_of(per.end)
    res.tax_year = label
    pl = [t for t in data.transactions if per.start <= t.date <= per.end and t.side in ("income", "expense")]
    income = sum(t.net for t in pl if t.side == "income")
    expenses = sum(t.net for t in pl if t.side == "expense")
    res.accounting_profit = income - expenses
    add("acc_profit", "Net profit per the accounts", res.accounting_profit, ["SA-PROFIT-01"],
        detail=[f"Income {fmt(income)} less expenses {fmt(expenses)} from {len(pl)} ledger lines"])
    routed = [t for t in treatments if t.category != "fixed_assets"]
    net_by_id = {t.id: t.net for t in pl}
    blocked_ts = [t for t in routed if t.txn_id in net_by_id and t.amount != net_by_id[t.txn_id]]
    if blocked_ts:
        add("vat_blocked", "Less: irrecoverable input tax posted to the VAT account", -sum(t.amount - net_by_id[t.txn_id] for t in blocked_ts),
            sorted({r for t in blocked_ts for r in t.rules}), txn_ids=[t.txn_id for t in blocked_ts])
    groups: Dict[str, List[Treatment]] = {}
    for t in routed:
        if t.disallowed and t.ct not in ("taxable", "non_trading"):
            groups.setdefault(t.rules[0], []).append(t)
    for rid, ts in sorted(groups.items()):
        amt = sum(t.disallowed for t in ts)
        uses = {(u.key, u.year): u for t in ts for u in t.params}
        add(f"addback_{rid}", ("Add: " if amt > 0 else "Less: ") + rule(rid).title.lower(), amt, sorted({x for t in ts for x in t.rules if not x.startswith("VAT-")}),
            params=list(uses.values()), txn_ids=[t.txn_id for t in ts], review_ids=sorted({t.review_id for t in ts if t.review_id}),
            provisional=any(t.provisional for t in ts),
            detail=[f"{t.date.isoformat()} {t.description}: {fmt(t.disallowed)}" + (f" ({t.note})" if t.note else "") for t in ts][:40])
    savings = sum(t.amount for t in routed if t.ct == "non_trading")
    if savings:
        add("less_savings", "Less: bank interest (savings income, outside the trading computation)", -savings, ["INC-INT-02"])
        ctx.flag("INC-INT-02", "info", f"Savings interest of {fmt(savings)} excluded from trading profits; savings income is not computed in v1.")
    if ca.charges:
        add("ca_charges", "Add: balancing charges", ca.charges, ["CA-DISP-01"])
    for ln in ca.lines:
        if not ln.key.startswith("ca_bc"):
            res.lines.append(ln.model_copy(update={"amount": -ln.amount, "label": "Less: " + ln.label[0].lower() + ln.label[1:]}))
    adjusted = res.accounting_profit + sum(ln.amount for ln in res.lines[1:])
    full = per.end >= twelve_months_from(per.start) - timedelta(days=0) and days_incl(per.start, per.end) >= 365
    basis_rules = ["SA-BASIS-01"]
    if not (aligned and full):
        ctx.flag("SA-BASIS-01", "warning", "Accounting period is not aligned to the tax year (or is not 12 months): the tax-year profit is estimated by time-apportionment of this period only.")
        ty_start, ty_end = tax_year_bounds(label)
        adjusted = muldiv(adjusted, days_incl(ty_start, ty_end), days_incl(per.start, per.end))
    if label == "2023-24" and not aligned:
        ctx.add_review(rule("SA-BASIS-02"), "transition", "2023-24 transition profit", proposed={"transition_profit": 0})
        basis_rules.append("SA-BASIS-02")
    if st.trading_status == "uncertain":
        ctx.add_review(rule("SA-BADGES-01"), "trade", "Is this activity a trade?", proposed={"trade": True})
    res.taxable_profit = max(0, adjusted)
    add("taxable_profit", f"Taxable trading profit {label}", res.taxable_profit, ["SA-PROFIT-01"] + basis_rules, kind="subtotal")
    if adjusted < 0:
        ctx.flag("SA-PROFIT-01", "info", f"Trading loss of {fmt(-adjusted)}: loss relief claims (ITA 2007 s64, s83) are elections not computed in v1.")

    # ---- income tax and NIC
    ty, ty_uses = ty_model(ctx, label)
    bands, band_use = region_bands(ctx, c.region, label)
    it = taxmath.income_tax(res.taxable_profit + st.other_income, 0, bands, ty)
    res.it_detail = it
    region_rule = {"scotland": ["EXT-IT-SCO-01"], "wales": ["EXT-IT-WAL-01"]}.get(c.region, [])
    pick = lambda *keys: [u for u in ty_uses if u.key in keys]   # noqa: E731
    if st.other_income:
        add("other_income", "Add: other non-savings income", st.other_income, ["SA-IT-01"])
    add("pa", "Less: personal allowance", -it["pa"], ["SA-IT-01", "EXT-PA-01"], params=pick("it.personal_allowance", "it.pa_taper_threshold"))
    add("taxable_income", "Taxable income", it["taxable_nonsav"], ["SA-IT-01"], kind="subtotal")
    for r in it["rows_nonsav"]:
        add(f"it_{r['band']}", f"Income tax: {fmt(r['amount'])} at {r['rate_bp'] / 100:g}% ({r['band']} rate, {c.region.replace('_', ' ').title()})", r["tax"],
            ["SA-IT-01"] + region_rule, params=[band_use])
    res.income_tax = it["total"]
    add("income_tax", "Income tax", res.income_tax, ["SA-IT-01"], kind="subtotal")
    res.class4 = taxmath.class4(res.taxable_profit, ty)
    add("class4", f"Class 4 NIC ({ty['c4_main_bp'] / 100:g}% between {fmt(ty['c4_lower'])} and {fmt(ty['c4_upper'])}, {ty['c4_add_bp'] / 100:g}% above)", res.class4,
        ["SA-C4-01"], params=pick("nic.class4.lower_profits_limit", "nic.class4.upper_profits_limit", "nic.class4.main_rate", "nic.class4.additional_rate"))
    res.class2 = taxmath.class2(res.taxable_profit, ty)
    spt_u = ctx.params.get("nic.class2.small_profits_threshold", tax_year_bounds(label)[0])
    spt = to_pence(spt_u.value)
    if res.class2:
        res.class2_status = "payable"
    elif res.taxable_profit >= spt:
        res.class2_status = "credited (no payment due)"
    else:
        res.class2_status = f"voluntary - {fmt(ty['c2_weekly'] * 52)} for the year protects the NI record"
    add("class2", f"Class 2 NIC: {res.class2_status}", res.class2, ["SA-C2-01"], params=pick("nic.class2.compulsory", "nic.class2.weekly_rate") + [spt_u])
    res.total = res.income_tax + res.class4 + res.class2
    add("total", f"Total income tax and NIC {label}", res.total, ["SA-IT-01", "SA-C4-01", "SA-C2-01"], kind="total")

    # ---- payments on account
    thr_u = ctx.params.get("sa.poa_threshold", tax_year_bounds(label)[0])
    src_u = ctx.params.get("sa.poa_at_source_pct", tax_year_bounds(label)[0])
    poa_base = res.income_tax + res.class4 - st.tax_deducted_at_source
    total_liab = res.income_tax + res.class4
    at_source_share = muldiv(st.tax_deducted_at_source, 10000, total_liab) if total_liab else 0
    if poa_base >= to_pence(thr_u.value) and at_source_share < bp(src_u.value):
        res.poa_next = muldiv(poa_base, 1, 2)
    res.balancing = res.total - st.tax_deducted_at_source - st.poas_paid_for_year
    end_year = int(label[:4]) + 1
    add("balancing", f"Balancing payment due 31 January {end_year} (after POAs paid of {fmt(st.poas_paid_for_year)})", res.balancing, ["SA-POA-01"], kind="note")
    add("poa", f"Payments on account for {end_year}-{str(end_year + 1)[2:]}: two of {fmt(res.poa_next)} (31 January and 31 July {end_year})",
        res.poa_next, ["SA-POA-01", "SA-POA-02"], kind="note", params=[thr_u, src_u])
    res.mtd = mtd(ctx, label, income)
    res.provisional = any(ln.provisional for ln in res.lines) or any(t.provisional for t in treatments)

    # ---- sole trader vs company comparator
    res.comparator_model = comparator_model(ctx, ctx.as_of, st.other_income)
    res.comparator = taxmath.compare_structures(res.taxable_profit, res.comparator_model)
    return res


def comparator_model(ctx: Ctx, on: date, other_income: int) -> Dict[str, Any]:
    c = ctx.client
    label = tax_year_of(on)
    ty, _ = ty_model(ctx, label)
    bands, _ = region_bands(ctx, c.region, label)
    start = tax_year_bounds(label)[0] - timedelta(days=5)        # a 12-month period from 1 April
    sched = ct_schedule(ctx, start, twelve_months_from(start), 0, planning=True)
    return {"tax_year": label, "ty": ty, "ns_bands": bands, "other_income": other_income,
            "admin_cost": to_pence(ctx.pol("comparator.extra_admin_cost", 0)),
            "ct_schedule": {"days": sched["days"], "slices": [{k: s[k] for k in ("fy", "days", "main_bp", "small_bp", "mr_num", "mr_den", "upper", "lower")} for s in sched["slices"]]}}


def mtd(ctx: Ctx, label: str, current_turnover: int) -> Dict[str, Any]:
    st = ctx.client.sole_trader
    u = ctx.params.get("mtd_itsa.schedule", tax_year_bounds(label)[0])
    rows, mandated_from = [], None
    current_ty = tax_year_of(ctx.as_of)
    turnover = dict(st.turnover_by_tax_year)
    turnover.setdefault(label, current_turnover)
    for s in u.value:
        ref = s["reference_year"]
        qi = turnover.get(ref)
        if qi is not None:
            qi += st.property_income_by_tax_year.get(ref, 0)
        thr = to_pence(s["threshold"])
        status = "unknown" if qi is None else ("in scope" if qi > thr else "not in scope")
        rows.append({"from": s["from_tax_year"], "reference_year": ref, "threshold": thr, "qualifying_income": qi, "status": status})
        if status == "in scope" and mandated_from is None:
            mandated_from = s["from_tax_year"]
    now = mandated_from is not None and mandated_from <= current_ty
    res = {"rows": rows, "mandated_from": mandated_from, "mandated_now": now, "software": st.mtd_software, "params": [u.model_dump()]}
    if now and not st.mtd_software:
        ctx.flag("SA-MTD-01", "serious", f"Within MTD for Income Tax from {mandated_from} but no compatible software recorded: quarterly updates are due.")
    elif now:
        ctx.flag("SA-MTD-01", "info", f"Within MTD for Income Tax from {mandated_from}; quarterly updates required.")
    elif mandated_from:
        ctx.flag("SA-MTD-01", "warning", f"Will be within MTD for Income Tax from {mandated_from} (qualifying income above the threshold).")
    return res
