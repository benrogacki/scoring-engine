"""Corporation tax computation.

Accounting profit -> tax adjustments (from the router's treatments) -> capital allowances -> losses ->
total profits -> qualifying charitable donations -> taxable total profits -> tax by financial year with
small profits rate / marginal relief, limits divided by associated companies and reduced for short
periods. Every line carries its rules, parameters, transactions and review items.

Rounding convention (documented in rule CT-SHORT-01): the period's upper and lower limits are reduced
for associates and short periods and rounded to the penny; profits and limits are allocated to each
financial year by days (remainder to the last slice); tax and marginal relief are rounded per slice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from ..dates import add_months, days_incl, fy_slices, twelve_months_from
from ..models import ClientData, Line, ParamUse, Treatment
from ..money import bp, fmt, muldiv, to_pence
from . import taxmath
from .capital_allowances import CAResult
from .context import Ctx

USES_RULES = ["CT-PROFIT-01", "CT-FY-01", "CT-RATE-01", "CT-SPR-01", "CT-MR-01", "CT-ASSOC-01", "CT-ASSOC-02",
              "CT-SHORT-01", "CT-LOSS-01", "CT-LOSS-02", "CT-QCD-01", "CT-PAY-01", "CT-RD-01", "INC-INT-01"]


@dataclass
class CTResult:
    lines: List[Line] = field(default_factory=list)
    accounting_profit: int = 0
    trading_profit: int = 0
    total_profits: int = 0
    ttp: int = 0
    augmented: int = 0
    ct: int = 0
    slices: List[Dict[str, Any]] = field(default_factory=list)
    schedule: Dict[str, Any] = field(default_factory=dict)
    losses_used: int = 0
    losses_cf: int = 0
    payment_due: Optional[date] = None
    pl_totals: Dict[str, int] = field(default_factory=dict)
    provisional: bool = False


def ct_schedule(ctx: Ctx, start: date, end: date, associated: int, planning: bool = False) -> Dict[str, Any]:
    """Financial-year slices with limits reduced for associates and short periods (pence).

    With ``planning`` a financial year that has no parameter file yet uses the latest year's values,
    and the schedule records which years were assumed."""
    slices = fy_slices(start, end)
    days = days_incl(start, end)
    full = end >= twelve_months_from(start)
    rows, uses, assumed = [], [], []
    latest_fy_end = max(date.fromisoformat(f.doc["financial_year"]["end"]) for f in ctx.params.files.values())
    for fy, s, e, d in slices:
        on = s
        if planning and s > latest_fy_end:
            on = latest_fy_end
            assumed.append(fy)
        get = lambda k, on=on: ctx.params.get(k, on)   # noqa: E731
        main, small, upper, lower, frac = (get(k) for k in ("ct.main_rate", "ct.small_profits_rate", "ct.upper_limit", "ct.lower_limit", "ct.mr_fraction"))
        uses += [main, small, upper, lower, frac]
        k = 1 + associated
        if full:
            u_ap, l_ap = muldiv(to_pence(upper.value), 1, k), muldiv(to_pence(lower.value), 1, k)
        else:
            u_ap, l_ap = muldiv(to_pence(upper.value), days, 365 * k), muldiv(to_pence(lower.value), days, 365 * k)
        rows.append({"fy": fy, "start": s.isoformat(), "end": e.isoformat(), "days": d, "main_bp": bp(main.value), "small_bp": bp(small.value),
                     "mr_num": int(frac.value["num"]), "mr_den": int(frac.value["den"]), "u_ap": u_ap, "l_ap": l_ap})
    if len({r["u_ap"] for r in rows}) == 1 and len({r["l_ap"] for r in rows}) == 1:
        us = taxmath._split(rows[0]["u_ap"], [r["days"] for r in rows])
        ls = taxmath._split(rows[0]["l_ap"], [r["days"] for r in rows])
    else:
        us = [muldiv(r["u_ap"], r["days"], days) for r in rows]
        ls = [muldiv(r["l_ap"], r["days"], days) for r in rows]
    for r, u, l in zip(rows, us, ls):
        r["upper"], r["lower"] = u, l
    return {"days": days, "full_year": full, "associated": associated, "slices": rows, "uses": uses, "assumed_fys": assumed}


def _sum(ts: List[Treatment], cat: str) -> int:
    return sum(t.amount for t in ts if t.category == cat)


def compute(ctx: Ctx, data: ClientData, treatments: List[Treatment], ca: CAResult) -> CTResult:
    c = ctx.client
    per = c.period
    res = CTResult()
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

    pl = [t for t in data.transactions if per.start <= t.date <= per.end and t.side in ("income", "expense")]
    income = sum(t.net for t in pl if t.side == "income")
    expenses = sum(t.net for t in pl if t.side == "expense")
    res.accounting_profit = income - expenses
    res.pl_totals = {"income": income, "expenses": expenses}
    add("acc_profit", "Profit before tax per the accounts", res.accounting_profit, ["CT-PROFIT-01"],
        detail=[f"Income {fmt(income)} less expenses {fmt(expenses)} from {len(pl)} ledger lines"])

    routed = [t for t in treatments if t.category != "fixed_assets"]
    net_by_id = {t.id: t.net for t in pl}
    blocked_ts = [t for t in routed if t.txn_id in net_by_id and t.amount != net_by_id[t.txn_id]]
    blocked = sum(t.amount - net_by_id[t.txn_id] for t in blocked_ts)
    if blocked:
        add("vat_blocked", "Less: irrecoverable input tax posted to the VAT account (accounts correction)", -blocked,
            sorted({r for t in blocked_ts for r in t.rules}), txn_ids=[t.txn_id for t in blocked_ts],
            detail=[f"{t.date.isoformat()} {t.description}: {fmt(t.amount - net_by_id[t.txn_id])}" for t in blocked_ts])

    # add-backs grouped by the deciding rule
    groups: Dict[str, List[Treatment]] = {}
    for t in routed:
        if t.disallowed and t.ct not in ("taxable", "non_trading"):
            groups.setdefault(t.rules[0], []).append(t)
    for rid, ts in sorted(groups.items()):
        amt = sum(t.disallowed for t in ts)
        r = rule(rid)
        uses = {(u.key, u.year): u for t in ts for u in t.params}
        add(f"addback_{rid}", ("Add: " if amt > 0 else "Less: ") + r.title.lower(), amt, sorted({x for t in ts for x in t.rules if not x.startswith("VAT-")}),
            params=list(uses.values()), txn_ids=[t.txn_id for t in ts], review_ids=sorted({t.review_id for t in ts if t.review_id}),
            provisional=any(t.provisional for t in ts),
            detail=[f"{t.date.isoformat()} {t.description}: {fmt(t.disallowed)}" + (f" ({t.note})" if t.note else "") for t in ts][:40])

    ntlr = sum(t.amount for t in routed if t.ct == "non_trading")
    if ntlr:
        add("less_ntlr", "Less: interest received (non-trading loan relationship credit)", -ntlr, ["INC-INT-01"],
            txn_ids=[t.txn_id for t in routed if t.ct == "non_trading"])
    if ca.charges:
        add("ca_charges", "Add: balancing charges", ca.charges, sorted({r for ln in ca.lines if ln.key.startswith("ca_bc") for r in ln.rules}))
    for ln in ca.lines:
        if ln.key.startswith("ca_bc"):
            continue
        res.lines.append(ln.model_copy(update={"amount": -ln.amount, "label": "Less: " + ln.label[0].lower() + ln.label[1:]}))
    adjustments = sum(ln.amount for ln in res.lines[1:])
    res.trading_profit = res.accounting_profit + adjustments
    add("trading_profit", "Trading profit / (loss)", res.trading_profit, ["CT-PROFIT-01"], kind="subtotal")

    # losses
    profit_after_losses = res.trading_profit
    if c.losses_bf and res.trading_profit > 0:
        res.losses_used = min(c.losses_bf, res.trading_profit)
        profit_after_losses -= res.losses_used
        add("losses_bf", "Less: trading losses brought forward", -res.losses_used, ["CT-LOSS-01"],
            detail=[f"Losses b/f {fmt(c.losses_bf)}; used {fmt(res.losses_used)}"])
    loss = -res.trading_profit if res.trading_profit < 0 else 0
    res.losses_cf = c.losses_bf - res.losses_used + loss
    trading_for_total = max(0, profit_after_losses)
    if loss:
        ctx.flag("CT-LOSS-02", "info", f"Trading loss of {fmt(loss)}: consider a claim against total profits of this period and the previous 12 months (s37), or carry forward.")
    if ntlr:
        add("ntlr", "Add: non-trading loan relationship credits", ntlr, ["INC-INT-01"])
    res.total_profits = trading_for_total + ntlr
    add("total_profits", "Total profits", res.total_profits, ["CT-PROFIT-01"], kind="subtotal")
    donations = sum(t.amount for t in routed if t.category == "donations")
    qcd = min(donations, res.total_profits)
    if qcd:
        add("qcd", "Less: qualifying charitable donations", -qcd, ["CT-QCD-01"],
            txn_ids=[t.txn_id for t in routed if t.category == "donations"])
    res.ttp = res.total_profits - qcd
    res.augmented = res.ttp + c.exempt_distributions
    add("ttp", "Taxable total profits", res.ttp, ["CT-PROFIT-01"], kind="total")
    if c.exempt_distributions:
        add("augmented", "Augmented profits (including exempt distributions)", res.augmented, ["CT-MR-01"], kind="note")

    # associated companies
    assoc = c.associated_companies or 0
    assoc_rules = ["CT-ASSOC-01"]
    assoc_review: List[str] = []
    if c.associated_basis == "uncertain":
        item = ctx.add_review(rule("CT-ASSOC-02"), "assoc", "Associated companies - control test", proposed={"associated_companies": assoc},
                              impact="Changes the upper and lower limits and so the rate of corporation tax.")
        assoc_review.append(item.id)
        dec = (item.decision or {}).get("outcome") or {}
        if "associated_companies" in dec:
            assoc = int(dec["associated_companies"])
        assoc_rules.append("CT-ASSOC-02")
    sched = ct_schedule(ctx, per.start, per.end, assoc)
    res.schedule = {k: v for k, v in sched.items() if k != "uses"}
    out = taxmath.ct_on_profit(res.ttp, res.augmented, sched)
    res.ct, res.slices = out["ct"], out["slices"]
    lim_rules = assoc_rules + ([] if sched["full_year"] else ["CT-SHORT-01"]) + (["CT-FY-01"] if len(out["slices"]) > 1 else [])
    lim_detail = [f"{len(sched['slices'])} financial year slice(s); {sched['days']} days; {assoc} associated compan{'y' if assoc == 1 else 'ies'}"]
    for s in sched["slices"]:
        lim_detail.append(f"FY{s['fy']}: {s['days']} days, upper limit {fmt(s['upper'])}, lower limit {fmt(s['lower'])}")
    add("limits", "Upper and lower limits for the period", 0, lim_rules, kind="note", params=sched["uses"], detail=lim_detail,
        review_ids=assoc_review, provisional=bool(assoc_review) and not any(r.decision for r in ctx.review if r.id in assoc_review))
    for s in out["slices"]:
        if s["n"] == 0 and res.ttp <= 0:
            continue
        rate_rule = {"small": "CT-SPR-01", "main": "CT-RATE-01", "marginal": "CT-RATE-01", "nil": "CT-RATE-01"}[s["rate"]]
        sl = next(x for x in sched["slices"] if x["fy"] == s["fy"])
        rate_bp = sl["small_bp"] if s["rate"] == "small" else sl["main_bp"]
        add(f"ct_fy{s['fy']}", f"FY{s['fy']} ({s['days']} days): {fmt(s['n'])} at {rate_bp / 100:g}%", s["tax"], [rate_rule] + (["CT-FY-01"] if len(out["slices"]) > 1 else []),
            params=[u for u in sched["uses"] if u.key in ("ct.main_rate", "ct.small_profits_rate")])
        if s["mr"]:
            sl_frac = f"{sl['mr_num']}/{sl['mr_den']}"
            add(f"mr_fy{s['fy']}", f"Less marginal relief FY{s['fy']}: ({fmt(s['upper'])} - {fmt(s['a'])}) x {sl_frac}" + ("" if s["a"] == s["n"] else " x N/A"),
                -s["mr"], ["CT-MR-01"], params=[u for u in sched["uses"] if u.key in ("ct.upper_limit", "ct.mr_fraction", "ct.lower_limit")])
    res.payment_due = add_months(per.end, 9) + timedelta(days=1)
    add("ct", "Corporation tax liability", res.ct, ["CT-PAY-01"], kind="total", detail=[f"Payable by {res.payment_due.isoformat()}"])
    res.provisional = any(ln.provisional for ln in res.lines) or any(t.provisional for t in treatments)

    # R&D detection (never computed)
    rd = [t for t in data.transactions if per.start <= t.date <= per.end and (t.category == "research_development" or
          any(w in t.description.lower() for w in ("prototype", "r&d", "research and development", "experimental")))]
    if rd:
        ctx.add_review(rule("CT-RD-01"), "rd", "Possible R&D relief claim", amount=sum(t.net for t in rd), txn_ids=[t.id for t in rd],
                       impact="No relief computed. A claim could reduce the CT liability or produce a credit.")
    return res
