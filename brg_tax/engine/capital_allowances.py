"""Capital allowances: pools, AIA, full expensing, first-year allowances, WDAs, SBA and disposals.

Additions and disposals come from the fixed asset register. Each addition is allocated in this order
under the default ("max") strategy, citing the rule on each line:

* company, new and unused main-rate plant          -> full expensing (CA-FE-01)
* zero-emission new car                             -> 100% FYA (CA-CAR-02)
* other cars                                        -> main or special pool by CO2 (CA-CAR-01), no AIA
* special-rate (integral features, long life)       -> AIA, then 50% FYA if new (company), then pool
* other plant (used, or unincorporated)             -> AIA, then 40% FYA where available, then main pool
* assets with private use (sole traders)            -> single-asset pool, allowances x business use (CA-CAR-03)
* buildings and structures                          -> SBA on qualifying cost (CA-SBA-01)

Other strategies for the optimiser: ``aia_first`` (AIA before full expensing) and ``wda_only``
(no AIA or first-year claims). Short periods scale the AIA limit, WDAs and the small pool limit by
days / 365; a WDA rate change inside the period gives a hybrid rate weighted by days.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from ..dates import days_incl, fy_slices, tax_years_spanned, tax_year_bounds, twelve_months_from
from ..models import Asset, Line, ParamUse
from ..money import at_rate, bp, muldiv
from .context import Ctx

USES_RULES = ["CA-PLANT-01", "CA-AIA-01", "CA-AIA-02", "CA-FE-01", "CA-FYA-SR-01", "CA-FYA40-01", "CA-CAR-01",
              "CA-CAR-02", "CA-CAR-03", "CA-INTF-01", "CA-WDA-01", "CA-WDA-02", "CA-SMALL-01", "CA-DISP-01",
              "CA-DISP-02", "CA-NEW-01", "CA-SBA-01"]
STRATEGIES = ("max", "aia_first", "wda_only")
SPECIAL_CLASSES = ("integral_feature", "long_life")
PLANT_CLASSES = ("plant", "computer", "van")


@dataclass
class CAResult:
    strategy: str
    lines: List[Line] = field(default_factory=list)
    allowances: int = 0             # total deduction
    charges: int = 0                # total balancing charges (addition to profit)
    aia_limit: int = 0
    aia_used: int = 0
    pools_cf: Dict[str, int] = field(default_factory=dict)
    single_pools: List[Dict[str, Any]] = field(default_factory=list)
    sba: List[Dict[str, Any]] = field(default_factory=list)
    schedule: List[Dict[str, Any]] = field(default_factory=list)    # per asset

    @property
    def net(self) -> int:
        return self.allowances - self.charges


def _segments(ctx: Ctx, start: date, end: date) -> List[Tuple[date, date, int]]:
    """Parameter segments for the period: CT by financial year, IT by tax year."""
    if ctx.client.entity_type == "company":
        return [(s, e, d) for _, s, e, d in fy_slices(start, end)]
    out = []
    for label in tax_years_spanned(start, end):
        ts, te = tax_year_bounds(label)
        s, e = max(start, ts), min(end, te)
        out.append((s, e, days_incl(s, e)))
    return out


def _full_year(start: date, end: date) -> bool:
    return end >= twelve_months_from(start)


def compute(ctx: Ctx, assets: List[Asset], start: date, end: date, strategy: str = "max",
            record_reviews: bool = True) -> CAResult:
    c = ctx.client
    company = c.entity_type == "company"
    pre = "ca.ct" if company else "ca.it"
    res = CAResult(strategy=strategy)
    days = days_incl(start, end)
    full = _full_year(start, end)
    denom_days = days if full else 365
    segs = _segments(ctx, start, end)

    def p(key: str, on: date) -> ParamUse:
        return ctx.params.get(key, on)

    def weighted_rate(key: str) -> Tuple[int, List[ParamUse]]:
        """Sum of rate_bp x days over parameter segments (divide by 10000 x denom_days)."""
        total, uses = 0, []
        for s, e, d in segs:
            u = p(key, s)
            uses.append(u)
            total += bp(u.value) * d
        return total, uses

    def line(key: str, label: str, amount: int, rules: List[str], params: List[ParamUse], assets_ids: List[str] = (),
             detail: List[str] = (), kind: str = "line", provisional: bool = False, review_ids: List[str] = ()) -> None:
        auth: List[str] = []
        for rid in rules:
            for a in ctx.rule(rid, end).authority:
                if a not in auth:
                    auth.append(a)
        res.lines.append(Line(key=key, label=label, amount=amount, kind=kind, rules=list(rules), authority=auth,
                              params=list(params), txn_ids=list(assets_ids), detail=list(detail), provisional=provisional,
                              review_ids=list(review_ids)))

    # ---- AIA limit (time-apportioned for short periods)
    aia_uses = [p(f"{pre}.aia_limit", s) for s, _, _ in segs]
    aia_limit = muldiv(sum(int(u.value) * 100 * d for u, (_, _, d) in zip(aia_uses, segs)), 1, denom_days)
    aia_review = None
    if company and (c.associated_companies or 0) > 0 and c.aia_shared_with_related is not False and record_reviews:
        r = ctx.rule("CA-AIA-02", end)
        aia_review = ctx.add_review(r, "aia", "AIA shared with an associated company?", impact="Changes the AIA available and so the capital allowances claimed.")
        dec = aia_review.decision or {}
        share = (dec.get("outcome") or {}).get("aia_share_pct")
        if share is not None:
            aia_limit = muldiv(aia_limit, int(share), 100)
    res.aia_limit = aia_limit
    aia_left = aia_limit if strategy != "wda_only" else 0

    main_bf, special_bf = c.pools_bf.main, c.pools_bf.special
    main_add = special_add = 0
    main_disp = special_disp = 0
    sba_assets: List[Asset] = []
    singles: List[Dict[str, Any]] = []
    fe_total = aia_main = aia_special = fya50 = fya40 = zec = 0
    fe_ids: List[str] = []
    aia_ids: List[str] = []
    fya_ids: List[str] = []
    special_fya_ids: List[str] = []
    charge_lines: List[Tuple[str, int, List[str]]] = []

    # AIA goes first to special-rate expenditure (it would otherwise get only 6%), then the main pool.
    additions = sorted([a for a in assets if not a.pool_bf and start <= a.date_acquired <= end],
                       key=lambda a: (0 if a.asset_class in SPECIAL_CLASSES else 1, a.date_acquired, a.id))

    for a in additions:
        row = {"id": a.id, "description": a.description, "cost": a.cost, "class": a.asset_class, "date": a.date_acquired.isoformat(),
               "allowance": 0, "pool": None, "rules": []}
        if a.asset_class == "land":
            row.update(pool="none", rules=["CA-PLANT-01"])
            res.schedule.append(row)
            continue
        if a.asset_class == "building":
            sba_assets.append(a)
            row.update(pool="sba", rules=["CA-SBA-01"])
            res.schedule.append(row)
            continue
        new = a.new_unused
        if company and new is None and a.asset_class != "car" and record_reviews:
            ctx.add_review(ctx.rule("CA-NEW-01", end), f"new:{a.id}", f"New and unused? {a.description}", kind="fact",
                           proposed={"new_unused": False}, amount=a.cost, txn_ids=[a.id])
        private = (not company) and a.private_use_pct > 0
        if a.asset_class == "car":
            if company and record_reviews:
                ctx.flag("CA-CAR-01", "info", f"{a.description}: a company car available to a director gives a car benefit (P11D) and Class 1A NIC - not computed in v1.")
            co2_max = int(p(f"{pre}.car_main_pool_co2_max", a.date_acquired).value)
            zero = p(f"{pre}.fya_zero_emission_car_rate", a.date_acquired)
            car_rule_live = ctx.rule("CA-CAR-02").effective.contains(a.date_acquired)
            if a.co2_gkm == 0 and new and car_rule_live and strategy != "wda_only" and not private:
                zec += a.cost
                fya_ids.append(a.id)
                row.update(pool="fya", allowance=a.cost, rules=["CA-CAR-02"])
            elif private:
                pool = "main" if (a.co2_gkm is not None and a.co2_gkm <= co2_max) else "special"
                singles.append({"asset": a, "pool_rate": pool, "bf": 0, "add": a.cost, "aia": 0})
                row.update(pool=f"single ({pool} rate)", rules=["CA-CAR-01", "CA-CAR-03"])
            elif a.co2_gkm is not None and a.co2_gkm <= co2_max:
                main_add += a.cost
                row.update(pool="main", rules=["CA-CAR-01"])
            else:
                special_add += a.cost
                row.update(pool="special", rules=["CA-CAR-01"])
            res.schedule.append(row)
            continue

        special = a.asset_class in SPECIAL_CLASSES
        remaining = a.cost
        allow = 0
        rules: List[str] = []
        if company and new and not special and strategy == "max":
            fe_total += remaining
            fe_ids.append(a.id)
            allow, remaining = remaining, 0
            rules.append("CA-FE-01")
        if remaining and aia_left and strategy != "wda_only":
            use = min(aia_left, remaining)
            aia_left -= use
            if private:
                pass  # AIA on a private-use asset is given in its single pool below
            elif special:
                aia_special += use
            else:
                aia_main += use
            aia_ids.append(a.id)
            allow += use
            remaining -= use
            rules.append("CA-AIA-01")
            if private:
                singles.append({"asset": a, "pool_rate": "special" if special else "main", "bf": 0, "add": a.cost, "aia": use})
                row.update(pool="single", allowance=use, rules=rules + ["CA-CAR-03"])
                res.schedule.append(row)
                continue
        if remaining and company and new and strategy == "aia_first" and not special:
            fe_total += remaining
            fe_ids.append(a.id)
            allow += remaining
            remaining = 0
            rules.append("CA-FE-01")
        if remaining and special and company and new and strategy != "wda_only":
            half = muldiv(remaining, bp(p("ca.ct.special_rate_fya", a.date_acquired).value), 10000)
            fya50 += half
            special_fya_ids.append(a.id)
            allow += half
            special_add += remaining - half
            remaining = 0
            rules.append("CA-FYA-SR-01")
        if remaining and not special and new and strategy != "wda_only":
            r40 = p(f"{pre}.fya_main_40_rate", a.date_acquired)
            if r40.value:
                amt = at_rate(remaining, bp(r40.value))
                fya40 += amt
                allow += amt
                main_add += remaining - amt
                remaining = 0
                rules.append("CA-FYA40-01")
        if remaining:
            if private:
                singles.append({"asset": a, "pool_rate": "special" if special else "main", "bf": 0, "add": a.cost, "aia": 0})
            elif special:
                special_add += remaining
            else:
                main_add += remaining
        if special:
            rules.append("CA-INTF-01")
        row.update(pool="special" if special else "main", allowance=allow, rules=rules or ["CA-WDA-01"])
        res.schedule.append(row)

    # ---- disposals
    for a in sorted([a for a in assets if a.disposal_date and start <= a.disposal_date <= end], key=lambda a: a.id):
        proceeds = a.disposal_proceeds or 0
        value = min(proceeds, a.cost)
        if company and a.claimed_fe:
            if a.asset_class in SPECIAL_CLASSES:
                half = muldiv(value, 1, 2)
                charge_lines.append((f"Balancing charge on 50% FYA asset {a.description} (s45U)", value - half, [a.id]))
                special_disp += half
            else:
                charge_lines.append((f"Balancing charge on full-expensed asset {a.description} (s45U)", value, [a.id]))
            continue
        if a.asset_class in SPECIAL_CLASSES or (a.asset_class == "car" and a.co2_gkm is not None and a.co2_gkm > 50):
            special_disp += value
        else:
            main_disp += value
        res.schedule.append({"id": a.id, "description": a.description, "cost": a.cost, "class": a.asset_class,
                             "date": a.disposal_date.isoformat(), "allowance": -value, "pool": "disposal", "rules": ["CA-DISP-01"]})

    # ---- lines: first-year and AIA
    if fe_total:
        line("ca_fe", "Full expensing (100% FYA) on new main-rate plant", fe_total, ["CA-FE-01"], [p("ca.ct.full_expensing_rate", end)], fe_ids)
    if zec:
        line("ca_zec", "100% FYA - zero-emission cars", zec, ["CA-CAR-02"], [p(f"{pre}.fya_zero_emission_car_rate", end)], fya_ids)
    rev_ids = [aia_review.id] if aia_review else []
    prov = bool(aia_review and not aia_review.decision)
    if aia_main or aia_special:
        line("ca_aia", "Annual investment allowance", aia_main + aia_special, ["CA-AIA-01"] + (["CA-AIA-02"] if aia_review else []),
             aia_uses, aia_ids, [f"AIA limit for the period £{aia_limit / 100:,.2f}" + ("" if full else f" ({days} days / 365)")],
             provisional=prov, review_ids=rev_ids)
    if fya50:
        line("ca_fya50", "50% special rate first-year allowance", fya50, ["CA-FYA-SR-01"], [p("ca.ct.special_rate_fya", end)], special_fya_ids)
    if fya40:
        line("ca_fya40", "40% first-year allowance (main rate)", fya40, ["CA-FYA40-01"], [p(f"{pre}.fya_main_40_rate", end)])

    # ---- pools
    small_limit_uses = [p(f"{pre}.small_pool_limit", s) for s, _, _ in segs]
    small_limit = muldiv(sum(int(u.value) * 100 * d for u, (_, _, d) in zip(small_limit_uses, segs)), 1, denom_days)

    def pool(name: str, bf: int, add: int, disp: int, rate_key: str, wda_rule: str, label: str) -> None:
        bal = bf + add - disp
        rate_sum, rate_uses = weighted_rate(rate_key)
        detail = [f"b/f £{bf / 100:,.2f}", f"additions £{add / 100:,.2f}", f"disposals £{disp / 100:,.2f}"]
        if bal < 0:
            line(f"ca_bc_{name}", f"Balancing charge - {label}", -bal, ["CA-DISP-01"], [], [], detail)
            res.charges += -bal
            res.pools_cf[name] = 0
            return
        if bal and bal <= small_limit and strategy != "wda_only":
            line(f"ca_small_{name}", f"Small pool allowance - {label}", bal, ["CA-SMALL-01"], small_limit_uses, [], detail)
            res.allowances += bal
            res.pools_cf[name] = 0
            return
        wda = muldiv(bal, rate_sum, 10000 * denom_days)
        if wda:
            rate_txt = ", ".join(f"{u.value}% ({u.year})" for u in rate_uses)
            line(f"ca_wda_{name}", f"WDA - {label}", wda, [wda_rule], rate_uses, [], detail + [f"rate {rate_txt}" + ("" if full else f", {days} days / 365")])
        res.allowances += wda
        res.pools_cf[name] = bal - wda

    res.allowances += fe_total + zec + aia_main + aia_special + fya50 + fya40
    res.aia_used = aia_main + aia_special + sum(s["aia"] for s in singles)
    pool("main", main_bf, main_add, main_disp, f"{pre}.wda_main_rate", "CA-WDA-01", "main pool")
    pool("special", special_bf, special_add, special_disp, f"{pre}.wda_special_rate", "CA-WDA-02", "special rate pool")

    # ---- single-asset pools (private use, unincorporated)
    for s in singles:
        a: Asset = s["asset"]
        business = 100 - a.private_use_pct
        bal = s["add"] - s["aia"]
        rate_sum, rate_uses = weighted_rate(f"{pre}.wda_{'main' if s['pool_rate'] == 'main' else 'special'}_rate")
        wda = muldiv(bal, rate_sum, 10000 * denom_days)
        gross = s["aia"] + wda
        allowed = muldiv(gross, business, 100)
        line(f"ca_single_{a.id}", f"Single-asset pool - {a.description} ({business}% business use)", allowed,
             ["CA-CAR-03"] + (["CA-AIA-01"] if s["aia"] else []), rate_uses + aia_uses[:1], [a.id],
             [f"AIA £{s['aia'] / 100:,.2f} + WDA £{wda / 100:,.2f} = £{gross / 100:,.2f}; private use {a.private_use_pct}% disallowed"])
        res.allowances += allowed
        res.single_pools.append({"id": a.id, "description": a.description, "cf": bal - wda, "allowance": allowed, "business_pct": business})

    # ---- SBA
    for b in sba_assets:
        _sba(ctx, res, line, b.id, b.description, b.qualifying_cost or b.cost, b.brought_into_use or b.date_acquired, start, end, pre)
    for b in c.buildings_bf:
        _sba(ctx, res, line, b.id, b.description, b.qualifying_cost, b.brought_into_use, start, end, pre)

    for label, amt, ids in charge_lines:
        line("ca_bc_fe", label, amt, ["CA-DISP-02"], [], ids)
        res.charges += amt
    return res


def _sba(ctx: Ctx, res: CAResult, line, aid: str, desc: str, cost: int, from_date: date, start: date, end: date, pre: str) -> None:
    s = max(start, from_date)
    if s > end:
        return
    d = days_incl(s, end)
    u = ctx.params.get(f"{pre}.sba_rate", end)
    amt = muldiv(cost * bp(u.value), d, 10000 * 365)
    line(f"ca_sba_{aid}", f"Structures and buildings allowance - {desc}", amt, ["CA-SBA-01"], [u], [aid],
         [f"£{cost / 100:,.2f} x {u.value}% x {d} days / 365"])
    res.allowances += amt
    res.sba.append({"id": aid, "description": desc, "qualifying_cost": cost, "days": d, "allowance": amt})


def all_strategies(ctx: Ctx, assets: List[Asset], start: date, end: date) -> Dict[str, int]:
    """Net allowances under each claim strategy (for the optimiser's CA choice)."""
    return {s: compute(ctx, assets, start, end, s, record_reviews=False).net for s in STRATEGIES}
