"""Pure tax arithmetic shared by the engine and mirrored line-for-line in dashboard/engine_mirror.js.

Inputs are plain dicts of integers (pence, basis points) built from the parameter files by
``extraction.build_model``; nothing here reads a parameter file or hard-codes a rate. Keep this file
and the JS mirror in step - tests/brg_tax/test_brg_parity.py runs both over a grid of inputs.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..money import at_rate, muldiv

Model = Dict[str, Any]


# --------------------------------------------------------------------------- income tax
def banded(amount: int, bands: List[Dict[str, Any]], start: int = 0) -> Dict[str, Any]:
    """Tax on ``amount`` of taxable income sitting above ``start``, through cumulative bands."""
    tax, pos, left, rows = 0, start, max(0, amount), []
    for b in bands:
        top = b["upto"]
        if top is not None and pos >= top:
            continue
        room = left if top is None else min(left, top - pos)
        if room <= 0:
            break
        t = at_rate(room, b["rate_bp"])
        rows.append({"band": b.get("name", ""), "amount": room, "rate_bp": b["rate_bp"], "tax": t})
        tax += t
        pos += room
        left -= room
        if left <= 0:
            break
    return {"tax": tax, "rows": rows}


def personal_allowance(total_income: int, ty: Model) -> int:
    pa = ty["pa"]
    excess = total_income - ty["taper"]
    if excess > 0:
        pa = max(0, pa - (excess // 200) * 100)      # £1 for every £2, in whole pounds
    return pa


def income_tax(nonsav: int, div: int, ns_bands: List[Dict[str, Any]], ty: Model) -> Dict[str, Any]:
    nonsav, div = max(0, nonsav), max(0, div)
    pa = personal_allowance(nonsav + div, ty)
    pa_ns = min(pa, nonsav)
    pa_div = min(pa - pa_ns, div)
    tns = nonsav - pa_ns
    tdiv = div - pa_div
    ns = banded(tns, ns_bands)
    # dividends: UK bands and rates, sitting on top of non-savings income; the allowance uses band
    nil = min(ty["div_allowance"], tdiv)
    pos = tns + nil
    left = tdiv - nil
    dtax, drows = 0, []
    for i, b in enumerate(ty["uk_bands"]):
        top = b["upto"]
        if left <= 0:
            break
        if top is not None and pos >= top:
            continue
        room = left if top is None else min(left, top - pos)
        rate = ty["div_bp"][min(i, len(ty["div_bp"]) - 1)]
        t = at_rate(room, rate)
        drows.append({"band": b.get("name", ""), "amount": room, "rate_bp": rate, "tax": t})
        dtax += t
        pos += room
        left -= room
    return {"pa": pa, "taxable_nonsav": tns, "taxable_div": tdiv, "div_nil": nil, "tax_nonsav": ns["tax"],
            "tax_div": dtax, "total": ns["tax"] + dtax, "rows_nonsav": ns["rows"], "rows_div": drows}


# --------------------------------------------------------------------------- NIC
def class1(salary: int, ty: Model) -> Dict[str, int]:
    s = max(0, salary)
    ee = at_rate(max(0, min(s, ty["uel"]) - ty["pt"]), ty["ee_main_bp"]) + at_rate(max(0, s - ty["uel"]), ty["ee_add_bp"])
    er = at_rate(max(0, s - ty["st"]), ty["er_bp"])
    return {"ee": ee, "er": er}


def class4(profit: int, ty: Model) -> int:
    p = max(0, profit)
    return at_rate(max(0, min(p, ty["c4_upper"]) - ty["c4_lower"]), ty["c4_main_bp"]) + at_rate(max(0, p - ty["c4_upper"]), ty["c4_add_bp"])


def class2(profit: int, ty: Model) -> int:
    """Compulsory Class 2 only (2023-24: profits at or above the lower profits limit)."""
    if ty["c2_compulsory"] and profit >= ty["c4_lower"]:
        return ty["c2_weekly"] * 52
    return 0


# --------------------------------------------------------------------------- corporation tax
def _split(total: int, parts: List[int]) -> List[int]:
    """Allocate ``total`` across slices by day counts, remainder to the last slice."""
    whole = sum(parts)
    out, used = [], 0
    for i, d in enumerate(parts):
        if i == len(parts) - 1:
            out.append(total - used)
        else:
            v = muldiv(total, d, whole)
            out.append(v)
            used += v
    return out


def ct_on_profit(n: int, a: int, sched: Model) -> Dict[str, Any]:
    """Corporation tax on taxable total profits ``n`` with augmented profits ``a``."""
    slices = sched["slices"]
    if n <= 0:
        return {"ct": 0, "slices": [{"fy": s["fy"], "days": s["days"], "n": 0, "a": 0, "rate": "nil", "tax": 0, "mr": 0, "ct": 0} for s in slices]}
    days = [s["days"] for s in slices]
    ns, as_ = _split(n, days), _split(max(a, n), days)
    total, rows = 0, []
    for s, ni, ai in zip(slices, ns, as_):
        if ai <= s["lower"]:
            tax, mr, rate = at_rate(ni, s["small_bp"]), 0, "small"
        elif ai >= s["upper"]:
            tax, mr, rate = at_rate(ni, s["main_bp"]), 0, "main"
        else:
            tax = at_rate(ni, s["main_bp"])
            mr = muldiv((s["upper"] - ai) * ni, s["mr_num"], s["mr_den"] * ai)
            rate = "marginal"
        rows.append({"fy": s["fy"], "days": s["days"], "n": ni, "a": ai, "upper": s["upper"], "lower": s["lower"],
                     "rate": rate, "tax": tax, "mr": mr, "ct": tax - mr})
        total += tax - mr
    return {"ct": total, "slices": rows}


# --------------------------------------------------------------------------- extraction scenario
def _shares(total: int, people: List[Model]) -> Dict[str, int]:
    holders = [p for p in people if p["share_bp"] > 0 and not p.get("waived")]
    out = {p["id"]: 0 for p in people}
    if not holders or total <= 0:
        return out
    weights = [p["share_bp"] for p in holders]
    for p, v in zip(holders, _split(total, weights)):
        out[p["id"]] = v
    return out


def scenario(model: Model, sc: Model) -> Dict[str, Any]:
    ty = model["ty"]
    people = model["people"]
    sal = {p["id"]: (sc["salaries"].get(p["id"], 0) if p["director"] else 0) for p in people}
    pen = {p["id"]: (sc["pensions"].get(p["id"], 0) if p["director"] else 0) for p in people}
    nic = {pid: class1(s, ty) for pid, s in sal.items()}
    er_dir = sum(v["er"] for v in nic.values())
    above_st = sum(1 for p in people if p["director"] and sal[p["id"]] > ty["st"])
    ea_eligible = model["other_employees_above_st"] > 0 or above_st >= 2
    er_gross = er_dir + model["other_employer_nic"]
    ea_used = min(ty["ea"], er_gross) if ea_eligible else 0
    n = model["profit_before_directors"] - sum(sal.values()) - sum(pen.values()) - er_dir + ea_used
    ct = ct_on_profit(n, n + model["exempt_distributions"], model["ct_schedule"])
    pat = n - ct["ct"]
    reserves = model["opening_reserves"] + pat
    d_total = max(0, sc["dividend_total"])
    divs = _shares(d_total, people)
    s455, rows = 0, []
    total_it, total_ee, value = 0, 0, 0
    for p in people:
        pid = p["id"]
        it_all = income_tax(p["other_income"] + sal[pid], divs[pid], p["ns_bands"], ty)
        it_base = income_tax(p["other_income"], 0, p["ns_bands"], ty)
        extra = it_all["total"] - it_base["total"]
        dla = model["dla_overdrawn"].get(pid, 0)
        cleared = min(dla, divs[pid]) if sc.get("clear_dla") else 0
        s455 += at_rate(max(0, dla - cleared), ty["s455_bp"])
        net = sal[pid] + divs[pid] - nic[pid]["ee"] - extra
        rows.append({"id": pid, "name": p["name"], "salary": sal[pid], "pension": pen[pid], "dividend": divs[pid],
                     "ee_nic": nic[pid]["ee"], "er_nic": nic[pid]["er"], "income_tax": extra, "tax_on_salary": it_all["tax_nonsav"] - it_base["tax_nonsav"],
                     "tax_on_dividends": it_all["tax_div"], "pa": it_all["pa"], "net_cash": net, "value": net + pen[pid],
                     "dla_cleared": cleared, "qualifying_year": sal[pid] >= ty["lel"], "aa_exceeded": pen[pid] > ty["aa"]})
        total_it += extra
        total_ee += nic[pid]["ee"]
        value += net + pen[pid]
    er_net = er_gross - ea_used
    total_tax = ct["ct"] + total_it + total_ee + er_net
    return {"taxable_profit": n, "ct": ct["ct"], "ct_slices": ct["slices"], "profit_after_tax": pat, "reserves": reserves,
            "dividend_total": d_total, "hard_stop": d_total > reserves, "ea_eligible": ea_eligible, "ea_used": ea_used,
            "er_nic_directors": er_dir, "er_nic_net": er_net, "ee_nic": total_ee, "income_tax": total_it,
            "total_tax": total_tax, "value": value, "retained": reserves - d_total, "s455": s455, "people": rows}


def salary_grid(ty: Model) -> List[int]:
    pts = {0, ty["lel"], ty["st"], ty["pt"], ty["uel"]}
    pts.update(k * 100000 for k in range(0, 101))
    return sorted(pts)


def dividend_for(model: Model, pat: int, reserves: int) -> int:
    keep = model["retain_pct"]
    return max(0, min(reserves, muldiv(max(0, pat), 100 - keep, 100)))


def optimise(model: Model) -> Dict[str, Any]:
    """Best uniform director salary on the grid, with dividends of the post-tax profit (policy retention)."""
    best: Optional[Dict[str, Any]] = None
    directors = [p for p in model["people"] if p["director"]]
    for s in salary_grid(model["ty"]):
        sc = {"salaries": {p["id"]: s for p in directors}, "pensions": dict(model["default"]["pensions"]),
              "dividend_total": 0, "clear_dla": model["default"]["clear_dla"]}
        probe = scenario(model, sc)
        sc["dividend_total"] = dividend_for(model, probe["profit_after_tax"], probe["reserves"])
        r = scenario(model, sc)
        if best is None or r["value"] > best["result"]["value"]:
            best = {"salary": s, "scenario": sc, "result": r}
    return best  # type: ignore[return-value]


# --------------------------------------------------------------------------- sole trader vs company
def sole_trader_tax(profit: int, cm: Model) -> Dict[str, Any]:
    ty = cm["ty"]
    it_all = income_tax(cm["other_income"] + profit, 0, cm["ns_bands"], ty)
    it_base = income_tax(cm["other_income"], 0, cm["ns_bands"], ty)
    c4 = class4(profit, ty)
    c2 = class2(profit, ty)
    it = it_all["total"] - it_base["total"]
    total = it + c4 + c2
    return {"income_tax": it, "class4": c4, "class2": c2, "total": total, "net": profit - total}


def company_model(profit: int, cm: Model) -> Model:
    return {"ty": cm["ty"], "profit_before_directors": profit - cm["admin_cost"], "exempt_distributions": 0,
            "ct_schedule": cm["ct_schedule"], "opening_reserves": 0, "other_employees_above_st": 0, "other_employer_nic": 0,
            "retain_pct": 0, "dla_overdrawn": {},
            "people": [{"id": "owner", "name": "Owner", "share_bp": 10000, "director": True, "other_income": cm["other_income"],
                        "ns_bands": cm["ns_bands"], "waived": False}],
            "default": {"pensions": {"owner": 0}, "clear_dla": False}}


def compare_structures(profit: int, cm: Model) -> Dict[str, Any]:
    st = sole_trader_tax(profit, cm)
    best = optimise(company_model(profit, cm))
    r = best["result"]
    ltd_total = r["total_tax"] + cm["admin_cost"]
    return {"profit": profit, "sole_trader": st, "company": {"salary": best["salary"], "dividend": r["dividend_total"], "ct": r["ct"],
            "income_tax": r["income_tax"], "ee_nic": r["ee_nic"], "er_nic": r["er_nic_net"], "admin_cost": cm["admin_cost"],
            "total": ltd_total, "net": r["value"]}, "difference": r["value"] - st["net"]}


# --------------------------------------------------------------------------- VAT schemes
def vat_compare(v: Model) -> Dict[str, Any]:
    standard = v["output_vat"] - v["input_vat"]
    turnover = v["sales_net"] + v["output_vat"]
    lct = v["relevant_goods"] < muldiv(turnover, v["lct_pct_bp"], 10000) or v["relevant_goods"] < v["lct_min"]
    rate = v["lct_rate_bp"] if lct else v["sector_bp"]
    if v["first_year"]:
        rate -= v["first_year_discount_bp"]
    frs = at_rate(turnover, rate)
    return {"standard": standard, "flat_rate": frs, "flat_rate_bp": rate, "limited_cost_trader": lct,
            "vat_inclusive_turnover": turnover, "saving": standard - frs}
