"""VAT monitoring: registration tests (historic and forward-look), deregistration, flat rate scheme
comparison with the limited cost trader test, cash and annual accounting eligibility, partial
exemption detection, and input tax the router found to be over-claimed in the books."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List

from ..dates import add_months
from ..models import ClientData, Treatment
from ..money import bp, fmt, muldiv, to_pence
from . import taxmath
from .context import Ctx
from .router import vat_registered_on

USES_RULES = ["VAT-REG-01", "VAT-REG-02", "VAT-DEREG-01", "VAT-FRS-01", "VAT-FRS-02", "VAT-CASH-01", "VAT-ANN-01", "VAT-PE-01",
              "VAT-REC-01"]


def _month_end(d: date) -> date:
    return add_months(date(d.year, d.month, 1), 1, month_end_rule=False) - timedelta(days=1)


def _sales(data: ClientData) -> List:
    return [t for t in data.transactions if t.category in ("sales", "other_income") and str(t.facts.get("exempt", "no")).lower() != "yes"
            and str(t.facts.get("outside_scope", "no")).lower() != "yes"]


def rolling_turnover(data: ClientData, as_of: date, months: int = 24) -> List[Dict[str, Any]]:
    sales = _sales(data)
    last = _month_end(as_of)
    if last > as_of:
        last = date(as_of.year, as_of.month, 1) - timedelta(days=1)
    out = []
    for i in range(months - 1, -1, -1):
        me = _month_end(add_months(date(last.year, last.month, 1), -i, month_end_rule=False))
        start = add_months(me, -12) + timedelta(days=1)
        out.append({"month_end": me.isoformat(), "rolling_12m": sum(t.net for t in sales if start <= t.date <= me),
                    "month": sum(t.net for t in sales if date(me.year, me.month, 1) <= t.date <= me)})
    return out


def monitor(ctx: Ctx, data: ClientData, treatments: List[Treatment]) -> Dict[str, Any]:
    c = ctx.client
    v = c.vat
    registered = vat_registered_on(ctx, ctx.as_of)
    roll = rolling_turnover(data, ctx.as_of)
    res: Dict[str, Any] = {"registered": registered, "scheme": v.scheme if registered else None, "rolling": roll, "tests": [], "model": None}
    warn = int(ctx.pol("vat.approaching_threshold_pct", 90))
    latest = roll[-1] if roll else None

    def thr(key: str, on: date) -> int:
        return to_pence(ctx.params.get(key, on).value)

    if not registered:
        breach = None
        for r in roll:
            me = date.fromisoformat(r["month_end"])
            if r["rolling_12m"] > thr("vat.registration_threshold", me):
                breach = r
                break
        if breach:
            me = date.fromisoformat(breach["month_end"])
            notify = me + timedelta(days=30)
            eff = add_months(date(me.year, me.month, 1), 2, month_end_rule=False)
            res["tests"].append({"rule": "VAT-REG-01", "result": "must register", "month_end": breach["month_end"], "turnover": breach["rolling_12m"],
                                 "threshold": thr("vat.registration_threshold", me), "notify_by": notify.isoformat(), "effective": eff.isoformat()})
            ctx.flag("VAT-REG-01", "critical", f"Taxable turnover {fmt(breach['rolling_12m'])} in the 12 months to {breach['month_end']} exceeded the registration threshold: "
                     f"notify HMRC by {notify.isoformat()}, registration effective {eff.isoformat()}.")
        elif latest:
            me = date.fromisoformat(latest["month_end"])
            t = thr("vat.registration_threshold", me)
            pct = muldiv(latest["rolling_12m"], 100, t)
            res["tests"].append({"rule": "VAT-REG-01", "result": "below threshold", "month_end": latest["month_end"], "turnover": latest["rolling_12m"],
                                 "threshold": t, "headroom": t - latest["rolling_12m"], "pct": pct})
            if pct >= warn:
                ctx.flag("VAT-REG-01", "warning", f"Rolling 12-month taxable turnover {fmt(latest['rolling_12m'])} is {pct}% of the {fmt(t)} threshold "
                         f"(headroom {fmt(t - latest['rolling_12m'])}). Monitor monthly; registration is needed at the end of any month the total exceeds the threshold.",
                         headroom=t - latest["rolling_12m"])
        if v.expected_next_30_days is not None:
            t = thr("vat.registration_threshold", ctx.as_of)
            hit = v.expected_next_30_days > t
            res["tests"].append({"rule": "VAT-REG-02", "result": "must register" if hit else "not triggered", "expected_30_days": v.expected_next_30_days, "threshold": t})
            if hit:
                ctx.flag("VAT-REG-02", "critical", f"Turnover expected in the next 30 days alone ({fmt(v.expected_next_30_days)}) exceeds the threshold: register now.")
    else:
        if v.expected_next_12_months is not None:
            t = thr("vat.deregistration_threshold", ctx.as_of)
            can = v.expected_next_12_months <= t
            res["tests"].append({"rule": "VAT-DEREG-01", "result": "may deregister" if can else "not eligible", "expected_12m": v.expected_next_12_months, "threshold": t})
            if can:
                ctx.flag("VAT-DEREG-01", "info", f"Expected turnover {fmt(v.expected_next_12_months)} is at or below the deregistration threshold {fmt(t)}: voluntary deregistration is an option.")
        res["model"] = _scheme_model(ctx, data, treatments)
        if res["model"]:
            cmp = taxmath.vat_compare(res["model"])
            res["frs"] = cmp
            res["tests"].append({"rule": "VAT-FRS-01", "result": "eligible" if res["model"]["eligible"] else "not eligible", **cmp})
            if res["model"]["eligible"] and cmp["saving"] > 0 and v.scheme != "flat_rate":
                ctx.flag("VAT-FRS-01", "info", f"Flat rate scheme ({cmp['flat_rate_bp'] / 100:g}%) would have cost {fmt(cmp['flat_rate'])} against {fmt(cmp['standard'])} "
                         f"under standard accounting - an annual saving of about {fmt(cmp['saving'])}.")
            if v.scheme == "flat_rate" and cmp["saving"] < 0:
                ctx.flag("VAT-FRS-01", "warning", f"The flat rate scheme cost about {fmt(-cmp['saving'])} more than standard accounting over the period.")
        turnover = res["model"]["sales_net"] if res["model"] else (latest["rolling_12m"] if latest else 0)
        for rid, key in (("VAT-CASH-01", "vat.cash_join_limit"), ("VAT-ANN-01", "vat.annual_join_limit")):
            lim = thr(key, ctx.as_of)
            res["tests"].append({"rule": rid, "result": "eligible" if turnover <= lim else "not eligible", "turnover": turnover, "limit": lim})
        if v.exempt_supplies:
            ctx.add_review(ctx.rule("VAT-PE-01"), "pe", "Partial exemption: exempt supplies recorded", proposed={"vat": "recover"})
        over = [t for t in treatments if t.vat and t.vat_treatment in ("blocked", "partial") and t.vat_recoverable < t.vat]
        if over:
            amt = sum(t.vat - t.vat_recoverable for t in over)
            res["overclaimed"] = {"amount": amt, "txn_ids": [t.txn_id for t in over], "rules": sorted({r for t in over for r in t.rules})}
            ctx.flag("VAT-REC-01", "serious", f"Input tax of {fmt(amt)} posted in the books is not recoverable ({', '.join(res['overclaimed']['rules'])}). "
                     "Correct it on the next return within the error-correction limits (VAT Notice 700/45).", txns=res["overclaimed"]["txn_ids"])
        gifts = [t for t in treatments if t.rules and t.rules[0] == "EXP-GIFT-02"]
        if gifts:
            ctx.flag("EXP-GIFT-02", "warning", f"{len(gifts)} gift(s) outside the conspicuous-advertisement exception: check output tax where gifts to one person exceed the VAT gift limit in 12 months.")
    return res


def _scheme_model(ctx: Ctx, data: ClientData, treatments: List[Treatment]) -> Dict[str, Any]:
    c = ctx.client
    per = c.period
    sales = [t for t in _sales(data) if per.start <= t.date <= per.end]
    sales_net = sum(t.net for t in sales)
    output_vat = sum(t.vat for t in sales)
    input_vat = sum(t.vat_recoverable for t in treatments)
    goods = sum(t.net + t.vat for t in data.transactions if per.start <= t.date <= per.end and
                (str(t.facts.get("relevant_goods", "")).lower() == "yes" or (t.category == "cost_of_sales" and str(t.facts.get("relevant_goods", "yes")).lower() != "no")))
    on = per.end
    p = lambda k: ctx.params.get(k, on)   # noqa: E731
    sectors = p("vat.frs_sector_rates").value
    sector = c.vat.frs_sector or ctx.pol("vat.default_frs_sector", "Any other activity not listed elsewhere")
    if sector not in sectors:
        ctx.flag("VAT-FRS-01", "warning", f"Flat rate sector {sector!r} is not in the parameter table; using 'Any other activity not listed elsewhere'.")
        sector = "Any other activity not listed elsewhere"
    join = to_pence(p("vat.frs_join_limit").value)
    return {"sales_net": sales_net, "output_vat": output_vat, "input_vat": input_vat, "relevant_goods": goods, "sector": sector,
            "sector_bp": bp(sectors[sector]), "lct_rate_bp": bp(p("vat.frs_lct_rate").value), "lct_pct_bp": bp(p("vat.frs_lct_goods_pct").value),
            "lct_min": to_pence(p("vat.frs_lct_goods_min").value), "first_year": bool(c.vat.frs_first_year),
            "first_year_discount_bp": bp(p("vat.frs_first_year_discount").value), "eligible": sales_net <= join, "join_limit": join,
            "sectors": {k: bp(v) for k, v in sectors.items()}}
