"""Director extraction optimiser, DLA monitor, IR35 and income-shifting screens (companies).

``build_model`` turns the parameter files and the client's figures into the integer model that both
``taxmath`` (Python) and ``dashboard/engine_mirror.js`` evaluate. The optimiser only varies elections
(salary, dividend, employer pension, clearing an overdrawn loan account by dividend); anything that
looks like avoidance is detected and routed to review, never proposed.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ..dates import add_months, days_incl, tax_year_bounds, tax_year_of, twelve_months_from
from ..models import ClientData, DLAEntry, ParamUse, Person
from ..money import at_rate, bp, fmt, muldiv, to_pence
from . import taxmath
from .context import Ctx
from .ct import CTResult, ct_schedule

USES_RULES = ["EXT-IT-01", "EXT-IT-SCO-01", "EXT-IT-WAL-01", "EXT-PA-01", "EXT-DIV-01", "EXT-DIV-02", "EXT-NIC-01",
              "EXT-NIC-02", "EXT-EA-01", "EXT-SAL-01", "EXT-PEN-01", "EXT-DLA-01", "EXT-DLA-02", "EXT-DLA-03",
              "EXT-DLA-04", "EXT-DLA-05", "EXT-IR35-01", "AA-464C-01", "AA-464C-02", "AA-SETTLE-01", "AA-WAIVER-01",
              "AA-GAAR-01", "EXT-TRIV-DIR-01"]
REGION_BANDS = {"england": "it.ruk.bands", "northern_ireland": "it.ruk.bands", "scotland": "it.sco.bands", "wales": "it.wal.bands"}


# --------------------------------------------------------------------------- parameter model
def bands_pence(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"upto": None if b["upto"] is None else int(b["upto"]) * 100, "rate_bp": bp(b["rate"]), "name": b.get("name", "")} for b in raw]


def ty_model(ctx: Ctx, label: str) -> Tuple[Dict[str, Any], List[ParamUse]]:
    """Tax-year figures as integers for taxmath (pence / basis points)."""
    d = tax_year_bounds(label)[0]
    uses: List[ParamUse] = []

    def g(k: str) -> Any:
        u = ctx.params.get(k, d)
        uses.append(u)
        return u.value

    m = {
        "label": label,
        "pa": to_pence(g("it.personal_allowance")), "taper": to_pence(g("it.pa_taper_threshold")),
        "div_allowance": to_pence(g("it.dividend_allowance")),
        "div_bp": [bp(g("it.dividend_ordinary_rate")), bp(g("it.dividend_upper_rate")), bp(g("it.dividend_additional_rate"))],
        "uk_bands": bands_pence(g("it.ruk.bands")),
        "pt": to_pence(g("nic.class1.pt")), "uel": to_pence(g("nic.class1.uel")), "st": to_pence(g("nic.class1.st")),
        "lel": to_pence(g("nic.class1.lel")), "ee_main_bp": bp(g("nic.class1.primary_main_rate_director")),
        "ee_add_bp": bp(g("nic.class1.primary_additional_rate")), "er_bp": bp(g("nic.class1.secondary_rate")),
        "ea": to_pence(g("nic.employment_allowance")), "s455_bp": bp(g("ct.s455_rate")), "aa": to_pence(g("pension.annual_allowance")),
        "c4_lower": to_pence(g("nic.class4.lower_profits_limit")), "c4_upper": to_pence(g("nic.class4.upper_profits_limit")),
        "c4_main_bp": bp(g("nic.class4.main_rate")), "c4_add_bp": bp(g("nic.class4.additional_rate")),
        "c2_compulsory": bool(g("nic.class2.compulsory")), "c2_weekly": to_pence(g("nic.class2.weekly_rate")),
    }
    return m, uses


def region_bands(ctx: Ctx, region: str, label: str) -> Tuple[List[Dict[str, Any]], ParamUse]:
    u = ctx.params.get(REGION_BANDS[region], tax_year_bounds(label)[0])
    return bands_pence(u.value), u


def share_bps(people: List[Person]) -> Dict[str, int]:
    total = sum(p.shares for p in people)
    if not total:
        return {p.id: 0 for p in people}
    vals = taxmath._split(10000, [p.shares for p in people])
    return {p.id: v for p, v in zip(people, vals)}


# --------------------------------------------------------------------------- DLA monitor
def _balance_series(entries: List[DLAEntry]) -> List[Tuple[date, int]]:
    bal, out = 0, []
    for e in sorted(entries, key=lambda e: e.date):
        bal += e.amount
        out.append((e.date, bal))
    return out


def _bal_on(series: List[Tuple[date, int]], d: date) -> int:
    b = 0
    for when, v in series:
        if when <= d:
            b = v
        else:
            break
    return b


def _tax_months(open_d: date, close_d: date, label: str) -> int:
    ts, _ = tax_year_bounds(label)
    n = 0
    for i in range(12):
        m_start = add_months(ts, i, month_end_rule=False)
        m_end = add_months(ts, i + 1, month_end_rule=False) - timedelta(days=1)
        if open_d <= m_start and m_end <= close_d:
            n += 1
    return n


def dla_monitor(ctx: Ctx, data: ClientData) -> Dict[str, Any]:
    c = ctx.client
    per = c.period
    due = add_months(per.end, 9) + timedelta(days=1)
    out: Dict[str, Any] = {"due_date": due.isoformat(), "people": [], "total_s455": 0}
    if not data.dla:
        return out
    rate_u = ctx.params.get("ct.s455_rate", per.end)
    amt_u = ctx.params.get("ct.s464c.amount", per.end)
    days_u = ctx.params.get("ct.s464c.days", per.end)
    arr_u = ctx.params.get("ct.s464c.arrangement_threshold", per.end)
    s464_amt, s464_days, s464_arr = to_pence(amt_u.value), int(days_u.value), to_pence(arr_u.value)
    by_person: Dict[str, List[DLAEntry]] = {}
    for e in data.dla:
        by_person.setdefault(e.person_id, []).append(e)
    for pid, entries in sorted(by_person.items()):
        person = next((p for p in c.people if p.id == pid), None)
        series = _balance_series(entries)
        ye = _bal_on(series, per.end)
        window_end = min(due - timedelta(days=1), ctx.as_of)
        post = sorted([e for e in entries if per.end < e.date <= window_end], key=lambda e: e.date)
        matched_total, findings = 0, []
        repaid = 0
        for r in post:
            if r.amount >= 0:
                continue
            amount = -r.amount
            repaid += amount
            if r.method in ("dividend", "salary", "bonus"):
                continue          # chargeable to income tax: excluded from s464C (s464C(4))
            if amount < s464_amt:
                continue
            later = [e for e in entries if e.amount > 0 and r.date < e.date <= r.date + timedelta(days=s464_days)]
            new = sum(e.amount for e in later)
            before = _bal_on(series, r.date - timedelta(days=1))
            if new >= s464_amt:
                m = min(amount, new)
                matched_total += m
                item = ctx.add_review(ctx.rule("AA-464C-01", r.date), f"{pid}:{r.date.isoformat()}", f"s464C: repayment redrawn within {s464_days} days ({person.name if person else pid})",
                                      kind="anti_avoidance", proposed={"matched": m}, amount=m,
                                      reasoning=f"{fmt(amount)} repaid on {r.date.isoformat()} and {fmt(new)} redrawn by {max(e.date for e in later).isoformat()}. "
                                                f"The repayment is matched to the new advance and does not reduce the s455 charge (s464C(1)).",
                                      impact=f"s455 on the matched amount: {fmt(at_rate(m, bp(rate_u.value)))}")
                findings.append({"rule": "AA-464C-01", "repayment": r.date.isoformat(), "amount": amount, "redrawn": new, "matched": m, "review_id": item.id})
            elif before >= s464_arr:
                later_any = sum(e.amount for e in entries if e.amount > 0 and e.date > r.date)
                if later_any >= s464_amt:
                    item = ctx.add_review(ctx.rule("AA-464C-02", r.date), f"{pid}:{r.date.isoformat()}", f"s464C(3): arrangements to redraw? ({person.name if person else pid})",
                                          kind="anti_avoidance", proposed={"treat_as_matched": True}, amount=amount)
                    dec = (item.decision or {}).get("outcome") or {}
                    m = 0 if dec.get("treat_as_matched") is False else min(amount, later_any)
                    matched_total += m
                    findings.append({"rule": "AA-464C-02", "repayment": r.date.isoformat(), "amount": amount, "matched": m, "review_id": item.id})
        effective_repaid = max(0, repaid - matched_total)
        base = max(0, ye - effective_repaid) if ye > 0 else 0
        s455 = at_rate(base, bp(rate_u.value))
        bik = _bik(ctx, entries, series, tax_year_of(per.end))
        status = "clear" if ye <= 0 else ("cleared" if base == 0 else ("payable" if ctx.as_of >= due else "exposure"))
        relief = add_months(add_months(per.end, 12), 9) + timedelta(days=1)
        row = {"person_id": pid, "name": person.name if person else pid, "year_end_balance": ye, "max_balance": max([0] + [v for _, v in series]),
               "repaid_since": repaid, "s464c_matched": matched_total, "s455_base": base, "s455": s455, "status": status,
               "s455_rate": rate_u.value, "findings": findings, "bik": bik,
               "s458_note": f"If repaid after {due.isoformat()}, s458 relief is claimable from {relief.isoformat()} (9 months and 1 day after the end of the period of repayment, assuming 12-month periods)." if base else "",
               "series": [{"date": d.isoformat(), "balance": v} for d, v in series]}
        out["people"].append(row)
        out["total_s455"] += s455
        if ye > 0:
            days_left = (due - ctx.as_of).days
            sev = "critical" if status == "payable" else ("serious" if days_left <= 90 else "warning")
            ctx.flag("EXT-DLA-01", sev, f"{row['name']}: loan account overdrawn {fmt(ye)} at {per.end.isoformat()}; s455 exposure {fmt(s455)} "
                     + (f"payable {due.isoformat()}" if status == "payable" else f"unless cleared by {due.isoformat()} ({days_left} days)"),
                     person=pid, due=due.isoformat())
    out["rule_ids"] = ["EXT-DLA-01", "EXT-DLA-02", "EXT-DLA-03", "EXT-DLA-04", "EXT-DLA-05"]
    return out


def _bik(ctx: Ctx, entries: List[DLAEntry], series: List[Tuple[date, int]], label: str) -> Dict[str, Any]:
    ts, te = tax_year_bounds(label)
    thr_u = ctx.params.get("loans.bik_threshold", ts)
    ori_u = ctx.params.get("loans.official_rate", ts)
    er_u = ctx.params.get("nic.class1.secondary_rate", ts)
    days_bal: List[Tuple[date, int]] = []
    d, total_days_bal, peak = ts, 0, 0
    while d <= te:
        b = max(0, _bal_on(series, d))
        peak = max(peak, b)
        total_days_bal += b
        d += timedelta(days=1)
    res = {"tax_year": label, "threshold": to_pence(thr_u.value), "peak": peak, "official_rate": ori_u.value, "applies": peak > to_pence(thr_u.value)}
    if not res["applies"]:
        res.update(averaging=0, alternative=0, benefit=0, class1a=0)
        return res
    open_bal = max(0, _bal_on(series, ts))
    open_d = ts
    if open_bal == 0:
        first = next(((w, v) for w, v in series if ts <= w <= te and v > 0), None)
        open_d, open_bal = first if first else (ts, 0)
    close_bal = max(0, _bal_on(series, te))
    close_d = te
    if close_bal == 0:
        last_pos = [w for w, v in series if ts <= w <= te and v <= 0]
        close_d = last_pos[-1] if last_pos else te
    months = _tax_months(open_d, close_d, label)
    rate = bp(ori_u.value)
    averaging = muldiv(muldiv(open_bal + close_bal, 1, 2) * rate * months, 1, 10000 * 12)
    alternative = muldiv(total_days_bal * rate, 1, 10000 * 365)
    interest_paid = sum(-e.amount for e in entries if e.method == "interest" and ts <= e.date <= te and e.amount < 0)
    benefit = max(0, averaging - interest_paid)
    res.update(open_date=open_d.isoformat(), open_balance=open_bal, close_date=close_d.isoformat(), close_balance=close_bal, months=months,
               averaging=averaging, alternative=alternative, interest_paid=interest_paid, benefit=benefit,
               class1a=at_rate(benefit, bp(er_u.value)), class1a_rate=er_u.value)
    return res


# --------------------------------------------------------------------------- model + optimiser
def build_model(ctx: Ctx, data: ClientData, ct: CTResult, dla: Dict[str, Any]) -> Dict[str, Any]:
    c = ctx.client
    per = c.period
    label = tax_year_of(ctx.as_of)
    ty, uses = ty_model(ctx, label)
    pl = [t for t in data.transactions if per.start <= t.date <= per.end]
    dir_sal = sum(t.net for t in pl if t.category == "directors_salary")
    dir_pen = sum(t.net for t in pl if t.category == "director_pension")
    er_nic = sum(t.net for t in pl if t.category == "employer_nic")
    p0 = ct.ttp + dir_sal + dir_pen + er_nic - c.payroll.other_employer_nic
    days = days_incl(per.start, per.end)
    if not ct.schedule.get("full_year", True):
        p0 = muldiv(p0, 365, days)
    nxt = per.end + timedelta(days=1)
    sched = ct_schedule(ctx, nxt, twelve_months_from(nxt), c.associated_companies or 0, planning=True)
    if sched["assumed_fys"]:
        ctx.flag("CT-RATE-01", "info", f"Planning period {nxt.isoformat()} to {twelve_months_from(nxt).isoformat()}: no parameters yet for "
                 f"FY{', FY'.join(str(f) for f in sched['assumed_fys'])}; the latest year's rates and limits are assumed.")
    dividends_paid = sum(abs(t.net) for t in pl if t.category == "dividends")
    reserves_cf = c.opening_reserves + ct.accounting_profit - ct.ct - dividends_paid
    bps = share_bps(c.people)
    people = []
    for p in c.people:
        bands, u = region_bands(ctx, p.region, label)
        uses.append(u)
        people.append({"id": p.id, "name": p.name, "share_bp": bps[p.id], "director": p.is_director, "region": p.region,
                       "other_income": p.other_income, "ns_bands": bands, "waived": p.dividend_waived})
    dla_over = {r["person_id"]: r["s455_base"] for r in dla.get("people", []) if r["s455_base"] > 0}
    model = {
        "client_id": c.id, "tax_year": label, "ty": ty,
        "profit_before_directors": p0, "exempt_distributions": c.exempt_distributions,
        "ct_schedule": {"days": sched["days"], "slices": [{k: s[k] for k in ("fy", "days", "main_bp", "small_bp", "mr_num", "mr_den", "upper", "lower")} for s in sched["slices"]]},
        "opening_reserves": reserves_cf, "other_employees_above_st": c.payroll.other_employees_above_st,
        "other_employer_nic": c.payroll.other_employer_nic, "retain_pct": int(ctx.pol("extraction.retain_pct", 0)),
        "dla_overdrawn": dla_over, "people": people,
        "default": {"salaries": {p.id: p.salary for p in c.people if p.is_director},
                    "pensions": {p.id: p.employer_pension for p in c.people if p.is_director},
                    "clear_dla": bool(ctx.pol("extraction.clear_dla_by_dividend", True))},
    }
    return {"model": model, "uses": uses, "dividends_paid": dividends_paid, "reserves_cf": reserves_cf,
            "p0_basis": {"ttp": ct.ttp, "directors_salary": dir_sal, "director_pension": dir_pen, "employer_nic": er_nic,
                         "other_employer_nic": c.payroll.other_employer_nic, "annualised": not ct.schedule.get("full_year", True)}}


def optimise(ctx: Ctx, data: ClientData, ct: CTResult, dla: Dict[str, Any]) -> Dict[str, Any]:
    c = ctx.client
    built = build_model(ctx, data, ct, dla)
    model = built["model"]
    probe = taxmath.scenario(model, {**model["default"], "dividend_total": 0})
    default_sc = {**model["default"], "dividend_total": taxmath.dividend_for(model, probe["profit_after_tax"], probe["reserves"])}
    default = taxmath.scenario(model, default_sc)
    best = taxmath.optimise(model)

    # flags that are about the law, not the optimum
    if not default["ea_eligible"] and c.payroll.other_employees_above_st == 0 and len(c.directors) == 1:
        ctx.flag("EXT-EA-01", "info", "Employment Allowance not available: the sole director is the only employee paid above the secondary threshold.")
    for row in best["result"]["people"]:
        if row["aa_exceeded"]:
            ctx.flag("EXT-PEN-01", "warning", f"{row['name']}: employer pension contribution exceeds the annual allowance (carry forward not modelled).")
    # reserves check on dividends actually paid in the computed period
    available = c.opening_reserves + ct.accounting_profit - ct.ct
    if built["dividends_paid"] > available:
        ctx.flag("EXT-DIV-02", "critical", f"Dividends paid {fmt(built['dividends_paid'])} exceed estimated distributable reserves {fmt(available)}: possible unlawful dividend (CA 2006 s830). Hard stop.")
    if any(p.dividend_waived for p in c.people):
        ctx.add_review(ctx.rule("AA-WAIVER-01"), "waiver", "Dividend waiver recorded", kind="anti_avoidance")
    _settlements(ctx)
    _trivial_cap(ctx, data)
    return {"model": model, "default": {"scenario": default_sc, "result": default},
            "best": {"salary": best["salary"], "scenario": best["scenario"], "result": best["result"]},
            "saving": best["result"]["value"] - default["value"],
            "p0_basis": built["p0_basis"], "reserves_cf": built["reserves_cf"], "dividends_paid": built["dividends_paid"],
            "params": [u.model_dump() for u in _dedupe(built["uses"])],
            "rules": ["EXT-SAL-01", "EXT-PEN-01", "EXT-DIV-01", "EXT-DIV-02", "EXT-NIC-01", "EXT-EA-01", "EXT-PA-01", "EXT-DLA-05", "AA-GAAR-01"]}


def _settlements(ctx: Ctx) -> None:
    c = ctx.client
    workers = {p.id for p in c.people if p.works_in_business}
    for p in c.people:
        if p.shares and not p.works_in_business and (p.share_class != "ordinary" or p.connected_to in workers):
            reasons = []
            if p.share_class != "ordinary":
                reasons.append(f"holds {p.share_class} shares (a separate class)")
            if p.connected_to:
                reasons.append(f"connected to {p.connected_to}, who works in the business")
            ctx.add_review(ctx.rule("AA-SETTLE-01"), p.id, f"Settlements legislation: {p.name}", kind="anti_avoidance",
                           reasoning=f"{p.name} {' and '.join(reasons)} and does not work in the business. Dividends to them may be taxed on the settlor (ITTOIA s624).")


def _trivial_cap(ctx: Ctx, data: ClientData) -> None:
    """Trivial benefits to a director (tagged person=<id> on staff_gifts) above the annual cap (ITEPA s323B)."""
    totals: Dict[Tuple[str, str], int] = {}
    for t in data.transactions:
        pid = t.facts.get("person")
        if t.category == "staff_gifts" and pid and any(p.id == pid and p.is_director for p in ctx.client.people):
            k = (str(pid), tax_year_of(t.date))
            totals[k] = totals.get(k, 0) + t.net
    for (pid, label), amt in sorted(totals.items()):
        cap = to_pence(ctx.params.get("exp.trivial_benefit_director_cap", tax_year_bounds(label)[0]).value)
        if amt > cap:
            ctx.flag("EXT-TRIV-DIR-01", "warning", f"Trivial benefits to director {pid} in {label} total {fmt(amt)}, above the {fmt(cap)} cap: the excess benefits are taxable.")


def ir35(ctx: Ctx, data: ClientData, ct: CTResult) -> List[Dict[str, Any]]:
    c = ctx.client
    out = []
    if not c.contracts:
        return out
    per = c.period
    sales = sum(t.net for t in data.transactions if per.start <= t.date <= per.end and t.category == "sales")
    label = tax_year_of(per.end)
    ty, _ = ty_model(ctx, label)
    director = c.directors[0] if c.directors else None
    for i, k in enumerate(c.contracts):
        if k.client_size == "medium_large" and k.sds != "none":
            ctx.flag("EXT-IR35-01", "info", f"{k.end_client}: status determined by the client ({k.sds}) under Chapter 10; check fees were received net of PAYE if inside.")
            continue
        income = muldiv(sales, k.share_of_income_pct, 100)
        est = _deemed_payment(ctx, data, income, ty, director, label)
        item = ctx.add_review(ctx.rule("EXT-IR35-01", per.end), f"contract{i}", f"Employment status: {k.end_client}", amount=income,
                              proposed={"status": "outside", "deemed_payment": 0},
                              impact=(f"If inside IR35 (Chapter 8): deemed payment about {fmt(est['deemed_payment'])}, employer NIC {fmt(est['er_nic'])}, "
                                      f"extra income tax and NIC for the director about {fmt(est['extra_personal'])}. The deemed payment and its NIC are deductible for CT."),
                              extra_factors=[f"Client size recorded as {k.client_size}; SDS: {k.sds}; via agency: {'yes' if k.via_agency else 'no'}"])
        out.append({"contract": k.model_dump(), "income": income, "estimate": est, "review_id": item.id})
    return out


def _deemed_payment(ctx: Ctx, data: ClientData, income: int, ty: Dict[str, Any], director: Optional[Person], label: str) -> Dict[str, Any]:
    per = ctx.client.period
    pl = [t for t in data.transactions if per.start <= t.date <= per.end]
    salary = sum(t.net for t in pl if t.category == "directors_salary")
    er_paid = sum(t.net for t in pl if t.category == "employer_nic")
    pension = sum(t.net for t in pl if t.category == "director_pension")
    travel = sum(t.net for t in pl if t.category in ("travel", "subsistence") and str(t.facts.get("temporary_workplace", "")).lower() == "yes")
    r = income - muldiv(income, 5, 100) - travel - pension - er_paid - salary
    r = max(0, r)
    dp = muldiv(r, 10000, 10000 + ty["er_bp"])
    er = r - dp
    bands = region_bands(ctx, director.region if director else "england", label)[0]
    other = director.other_income if director else 0
    before = taxmath.income_tax(other + salary, 0, bands, ty)["total"] + taxmath.class1(salary, ty)["ee"]
    after = taxmath.income_tax(other + salary + dp, 0, bands, ty)["total"] + taxmath.class1(salary + dp, ty)["ee"]
    return {"relevant_income": income, "five_percent": muldiv(income, 5, 100), "expenses": travel, "pension": pension,
            "er_nic_paid": er_paid, "salary": salary, "residual": r, "deemed_payment": dp, "er_nic": er, "extra_personal": after - before,
            "authority": ["ITEPA 2003 s54"]}


def _dedupe(uses: List[ParamUse]) -> List[ParamUse]:
    seen, out = set(), []
    for u in uses:
        if (u.key, u.year) not in seen:
            seen.add((u.key, u.year))
            out.append(u)
    return out
