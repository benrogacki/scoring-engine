"""Deadline calendar generated per client from the rules in rules/deadlines.yaml (no hard-coded dates)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List

from ..dates import add_months, tax_year_bounds, tax_year_of, twelve_months_from
from ..rules import Rule
from .context import Ctx

USES_RULES = ["DL-CT600-01", "DL-CTPAY-01", "DL-S455-01", "DL-CHACC-01", "DL-CS-01", "DL-VAT-01", "DL-SA-01", "DL-SA-02",
              "DL-SA-03", "DL-MTD-01", "DL-P11D-01", "DL-C1A-01", "DL-P60-01", "DL-RTI-01"]
STAGGER_FIRST_MONTH = {"1": 3, "2": 4, "3": 5}


def _apply(rule: Rule, anchor: date) -> date:
    if rule.fixed:
        return date(anchor.year + rule.fixed.get("year_offset", 0), rule.fixed["month"], rule.fixed["day"])
    d = add_months(anchor, rule.offset.get("months", 0)) if rule.offset.get("months") else anchor
    return d + timedelta(days=rule.offset.get("days", 0))


def _vat_period_ends(stagger: str, start: date, end: date) -> List[date]:
    out = []
    d = date(start.year - 1, 1, 1)
    while d <= end:
        me = add_months(d, 1, month_end_rule=False) - timedelta(days=1)
        if stagger == "monthly" or (me.month - STAGGER_FIRST_MONTH[stagger]) % 3 == 0:
            if start <= me <= end:
                out.append(me)
        d = add_months(d, 1, month_end_rule=False)
    return out


def generate(ctx: Ctx, extra: Dict[str, Any]) -> List[Dict[str, Any]]:
    c = ctx.client
    lo = ctx.as_of - timedelta(days=int(ctx.pol("deadlines.look_back_days", 60)))
    hi = ctx.as_of + timedelta(days=int(ctx.pol("deadlines.look_ahead_days", 400)))
    soon = int(ctx.pol("deadlines.due_soon_days", 30))
    events: List[Dict[str, Any]] = []
    company = c.entity_type == "company"
    payroll = company and (c.payroll.operates or any(p.salary for p in c.directors))
    mtd_from = extra.get("mtd_from")

    def when_ok(rule: Rule) -> bool:
        return {"company": company, "sole_trader": not company, "vat_registered": c.vat.registered, "payroll": payroll,
                "mtd_itsa": bool(mtd_from), "s455": extra.get("s455", 0) > 0}.get(rule.when or "", True)

    # anchors
    period_ends = [p.end for p in c.periods]
    nxt = c.period.end + timedelta(days=1)
    period_ends.append(twelve_months_from(nxt))
    tax_year_ends = sorted({tax_year_bounds(tax_year_of(d))[1] for d in (ctx.as_of - timedelta(days=400), ctx.as_of - timedelta(days=30), ctx.as_of, ctx.as_of + timedelta(days=365))})
    review_dates = []
    if c.confirmation_statement_date:
        d = c.confirmation_statement_date
        while d <= hi:
            review_dates.append(d)
            d = add_months(d, 12, month_end_rule=False)
    vat_ends = []
    if c.vat.registered:
        start = max(c.vat.registration_date or lo - timedelta(days=60), lo - timedelta(days=60))
        vat_ends = _vat_period_ends(c.vat.stagger, start, hi)
    mtd_ends = []
    if mtd_from:
        ts = tax_year_bounds(mtd_from)[0]
        for i in range(0, 24):
            q = add_months(date(ts.year, 7, 5), 3 * i, month_end_rule=False)
            if q >= ts:
                mtd_ends.append(q)

    anchors = {"period_end": period_ends, "tax_year_end": tax_year_ends, "review_date": review_dates,
               "vat_period_end": vat_ends, "mtd_quarter_end": mtd_ends}
    for rule in ctx.rules.by_applies("deadline"):
        if c.entity_type not in rule.entity_types or not when_ok(rule):
            continue
        for a in anchors.get(rule.anchor or "", []):
            if rule.id == "DL-S455-01" and a != c.period.end:
                continue
            due = _apply(rule, a)
            if not rule.effective.contains(due) or not (lo <= due <= hi):
                continue
            label = {"period_end": f"period ended {a.isoformat()}", "tax_year_end": f"tax year {tax_year_of(a)}",
                     "review_date": f"review date {a.isoformat()}", "vat_period_end": f"VAT period ended {a.isoformat()}",
                     "mtd_quarter_end": f"quarter to {a.isoformat()}"}[rule.anchor]
            days = (due - ctx.as_of).days
            status = "past" if days < 0 else ("due_soon" if days <= soon else "upcoming")
            events.append({"id": f"{c.id}:{rule.id}:{a.isoformat()}", "client_id": c.id, "client": c.name, "rule": rule.id, "title": rule.title,
                           "for": label, "date": due.isoformat(), "kind": rule.kind, "days": days, "status": status,
                           "authority": rule.authority, "guidance": rule.guidance, "notes": rule.notes})
    if company and c.first_accounts and c.incorporated:
        ctx.flag("DL-CHACC-01", "warning", f"First accounts: Companies House deadline is 21 months after incorporation ({add_months(c.incorporated, 21).isoformat()}) if earlier than shown.")
    return sorted(events, key=lambda e: (e["date"], e["rule"]))
