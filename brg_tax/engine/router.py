"""Route each transaction through the rules library to a tax and VAT treatment.

For every profit-and-loss and fixed-asset transaction in the period the router builds a set of facts
(nominal-code defaults, the BRG Facts column, the client profile), finds every rule whose conditions
match, and picks the most specific one for the tax treatment and for VAT separately. ``judgment``
rules never resolve themselves: the item goes to the review queue and the rule's proposed default is
used provisionally until a reviewer decision is recorded.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from ..models import ParamUse, Transaction, Treatment
from ..money import at_rate, bp, muldiv, to_pence
from ..rules import Rule
from .context import Ctx

USES_RULES = ["VAT-NOTREG-01", "EXP-NORULE-01", "EXP-PRE-01", "EXP-MILE-01", "EXP-HOME-01"]
ROUTED_SIDES = ("income", "expense")


# --------------------------------------------------------------------------- facts and matching
def vat_registered_on(ctx: Ctx, d: date) -> bool:
    v = ctx.client.vat
    return bool(v.registered and (v.registration_date is None or v.registration_date <= d))


def facts_for(ctx: Ctx, t: Transaction) -> Dict[str, Any]:
    f: Dict[str, Any] = dict(t.facts)
    f["category"] = t.category
    f["entity_type"] = ctx.client.entity_type
    f["vat_registered"] = vat_registered_on(ctx, t.date)
    f["has_vat"] = t.vat != 0
    if "private_use_pct" in f and "business_use_pct" not in f:
        f["business_use_pct"] = 100 - int(f["private_use_pct"])
    st = ctx.client.sole_trader
    if "pre_trading" not in f and st and st.trading_start:
        f["pre_trading"] = "yes" if t.date < st.trading_start else "no"
    return f


def _operand(ctx: Ctx, rule: Rule, operand: Any, on: date, used: List[ParamUse]) -> Any:
    if isinstance(operand, str) and operand.startswith("param:"):
        u = ctx.params.get(operand[6:], on)
        used.append(u)
        return u.value
    return operand


def _cmp(fv: Any, op: str, ov: Any) -> bool:
    try:
        a, b = float(fv), float(ov)
    except (TypeError, ValueError):
        return False
    return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b, "eq": a == b, "ne": a != b}[op]


def _same(fv: Any, v: Any) -> bool:
    if isinstance(v, bool) or isinstance(fv, bool):
        return bool(fv) == bool(v) if isinstance(fv, bool) and isinstance(v, bool) else False
    return str(fv).strip().lower() == str(v).strip().lower()


def match_one(ctx: Ctx, rule: Rule, facts: Dict[str, Any], key: str, cond: Any, on: date, used: List[ParamUse]) -> bool:
    present = key in facts and facts[key] is not None and facts[key] != ""
    if isinstance(cond, list):
        return any(match_one(ctx, rule, facts, key, c, on, used) for c in cond)
    if isinstance(cond, dict):
        for op, operand in cond.items():
            if op == "missing":
                if bool(operand) == present:
                    return False
            elif op == "present":
                if bool(operand) != present:
                    return False
            else:
                if not present or not _cmp(facts[key], op, _operand(ctx, rule, operand, on, used)):
                    return False
        return True
    return present and _same(facts[key], cond)


def matches(ctx: Ctx, rule: Rule, facts: Dict[str, Any], on: date) -> Tuple[bool, List[ParamUse]]:
    used: List[ParamUse] = []
    for key, cond in rule.conditions.items():
        if not match_one(ctx, rule, facts, key, cond, on, used):
            return False, []
    return True, used


def best(cands: List[Tuple[Rule, List[ParamUse]]]) -> Optional[Tuple[Rule, List[ParamUse]]]:
    if not cands:
        return None
    return max(cands, key=lambda c: (c[0].specificity, c[0].priority))


# --------------------------------------------------------------------------- outcomes
class _Calc:
    """Running state for calculations that span transactions (mileage bands per person and tax year)."""

    def __init__(self) -> None:
        self.miles: Dict[Tuple[str, str], int] = {}


def _ct_amounts(ctx: Ctx, t: Transaction, facts: Dict[str, Any], outcome: Any, amount: int, calc: _Calc,
                used: List[ParamUse], notes: List[str]) -> Tuple[str, int, int]:
    """Return (label, allowable, disallowed) for a tax outcome on ``amount`` pence."""
    if outcome in ("allow", "taxable", "non_trading"):
        return outcome, amount, 0
    if outcome == "disallow":
        return "disallow", 0, amount
    if outcome == "capital":
        return "capital", 0, amount
    if isinstance(outcome, dict):
        if "allow_pct" in outcome:
            pct = int(outcome["allow_pct"])
            allow = muldiv(amount, pct, 100)
            return "partial", allow, amount - allow
        if "disallow_pct_fact" in outcome:
            pct = int(facts.get(outcome["disallow_pct_fact"], 0))
            dis = muldiv(amount, pct, 100)
            notes.append(f"{pct}% private/non-business use disallowed")
            return "partial", amount - dis, dis
        if "allow_pct_fact" in outcome:
            pct = int(facts.get(outcome["allow_pct_fact"], 100))
            allow = muldiv(amount, pct, 100)
            return "partial", allow, amount - allow
        if "disallow_pct_param" in outcome:
            rate, u = ctx.params.rate(outcome["disallow_pct_param"], t.date)
            used.append(u)
            dis = at_rate(amount, rate)
            notes.append(f"{u.value}% restriction")
            return "partial", amount - dis, dis
        calc_name = outcome.get("calc")
        if calc_name == "mileage":
            return _mileage(ctx, t, facts, amount, calc, used, notes)
        if calc_name == "home_flat_rate":
            return _home_flat(ctx, t, facts, amount, used, notes)
    raise ValueError(f"unknown tax outcome {outcome!r}")


def _mileage(ctx: Ctx, t: Transaction, facts: Dict[str, Any], amount: int, calc: _Calc,
             used: List[ParamUse], notes: List[str]) -> Tuple[str, int, int]:
    from ..dates import tax_year_of
    miles = int(facts.get("business_miles", 0))
    vehicle = str(facts.get("vehicle", "car")).lower()
    person = str(facts.get("person", "owner"))
    if vehicle in ("motorcycle", "bicycle"):
        u = ctx.params.get(f"exp.amap_{vehicle}_rate", t.date)
        used.append(u)
        amap = miles * int(u.value)
    else:
        first = ctx.params.get("exp.amap_car_first_rate", t.date)
        later = ctx.params.get("exp.amap_car_later_rate", t.date)
        limit = ctx.params.get("exp.amap_car_threshold_miles", t.date)
        used += [first, later, limit]
        k = (person, tax_year_of(t.date))
        before = calc.miles.get(k, 0)
        at_first = max(0, min(miles, int(limit.value) - before))
        calc.miles[k] = before + miles
        amap = at_first * int(first.value) + (miles - at_first) * int(later.value)
    notes.append(f"{miles:,} business miles; approved amount £{amap / 100:,.2f}")
    if ctx.client.entity_type == "company":
        if amount > amap:
            ctx.flag("EXP-MILE-01", "warning", f"Mileage paid exceeds the approved amount by £{(amount - amap) / 100:,.2f}: the excess is taxable earnings (report via payroll).", txn=t.id)
        return "allow", amount, 0
    allow = min(amount, amap)
    return ("allow" if allow == amount else "partial"), allow, amount - allow


def _home_flat(ctx: Ctx, t: Transaction, facts: Dict[str, Any], amount: int, used: List[ParamUse], notes: List[str]) -> Tuple[str, int, int]:
    u = ctx.params.get("exp.home_flat_rates", t.date)
    used.append(u)
    hours = int(facts.get("hours_per_month", 0))
    months = int(facts.get("months", 12))
    monthly = 0
    for band in u.value:
        if hours >= band["min_hours"] and (band["max_hours"] is None or hours <= band["max_hours"]):
            monthly = to_pence(band["monthly"])
    flat = monthly * months
    notes.append(f"{hours} hours/month for {months} months at £{monthly / 100:,.2f}/month = £{flat / 100:,.2f}")
    return ("allow" if flat == amount else "partial"), flat, amount - flat


def _vat_amounts(outcome: Any, facts: Dict[str, Any], vat: int) -> Tuple[str, int]:
    if outcome in ("recover",):
        return ("recover", vat) if vat else ("none", 0)
    if outcome in ("none", "not_registered", "blocked", "output_tax_check"):
        return outcome, 0
    if isinstance(outcome, dict):
        if "recover_pct" in outcome:
            return "partial", muldiv(vat, int(outcome["recover_pct"]), 100)
        if "recover_pct_fact" in outcome:
            return "partial", muldiv(vat, int(facts.get(outcome["recover_pct_fact"], 100)), 100)
    raise ValueError(f"unknown VAT outcome {outcome!r}")


def _apply_decision_ct(dec: Dict[str, Any], proposed: Any) -> Any:
    out = dec.get("outcome") or {}
    if dec.get("decision") == "accept" or "ct" not in out:
        return proposed
    return out["ct"]


def _apply_decision_vat(dec: Dict[str, Any], proposed: Any) -> Any:
    out = dec.get("outcome") or {}
    if dec.get("decision") == "accept" or "vat" not in out:
        return proposed
    return out["vat"]


# --------------------------------------------------------------------------- main entry
def route(ctx: Ctx, txns: List[Transaction], period_start: date, period_end: date) -> List[Treatment]:
    calc = _Calc()
    out: List[Treatment] = []
    notreg = ctx.rule("VAT-NOTREG-01")
    for t in sorted(txns, key=lambda x: (x.date, x.id)):
        if not (period_start <= t.date <= period_end):
            continue
        if t.side not in ROUTED_SIDES and t.category != "fixed_assets":
            continue
        facts = facts_for(ctx, t)
        rules = ctx.rules.transaction_rules(t.date, ctx.client.entity_type)
        ct_c, vat_c, overlays = [], [], []
        for r in rules:
            ok, used = matches(ctx, r, facts, t.date)
            if not ok:
                continue
            if r.overlay:
                overlays.append((r, used))
            elif "ct" in r.outcome:
                ct_c.append((r, used))
            if "vat" in r.outcome and not r.overlay:
                vat_c.append((r, used))
        ct_pick = best(ct_c)
        assert ct_pick is not None  # EXP-NORULE-01 matches everything
        ct_rule, ct_used = ct_pick
        if not facts["vat_registered"]:
            vat_pick: Optional[Tuple[Rule, List[ParamUse]]] = (notreg, [])
        else:
            vat_pick = best([c for c in vat_c if c[0].id != "VAT-NOTREG-01"])
        params_used: List[ParamUse] = list(ct_used)
        notes: List[str] = []
        rules_applied = [ct_rule.id]
        authority = list(ct_rule.authority)
        review_id, provisional, decision = None, False, None

        # ---- tax outcome (judgment and missing facts use the proposed default)
        ct_outcome = ct_rule.outcome["ct"]
        if ct_rule.certainty == "judgment" or ct_outcome in ("review", "review_fact"):
            kind = "fact" if ct_outcome == "review_fact" else "judgment"
            proposed = dict(ct_rule.default)
            item = ctx.add_review(
                ct_rule, t.id, f"{ct_rule.title}: {t.description or t.account}", kind=kind, proposed=proposed,
                amount=t.net, txn_ids=[t.id],
                question=(f"Record '{ct_rule.fact_needed}' for this transaction. " + ct_rule.question) if kind == "fact" else ct_rule.question,
            )
            review_id, decision = item.id, item.decision
            ct_outcome = proposed.get("ct", "allow") if ct_outcome in ("review", "review_fact") else ct_outcome
            if decision:
                ct_outcome = _apply_decision_ct(decision, ct_outcome)
            else:
                provisional = True

        # ---- VAT outcome
        vat_rule = vat_pick[0] if vat_pick else None
        vat_label, vat_rec = "n/a", 0
        blocked_cost = 0
        if t.side == "income":
            vat_label = "n/a"
        elif vat_rule is not None:
            params_used += vat_pick[1]
            if vat_rule.id not in rules_applied:
                rules_applied.append(vat_rule.id)
                authority += [a for a in vat_rule.authority if a not in authority]
            vo = vat_rule.outcome["vat"]
            if vo == "review_fact":
                proposed_vat = vat_rule.default.get("vat", "blocked")
                if vat_rule.id != ct_rule.id:
                    item = ctx.add_review(vat_rule, t.id, f"{vat_rule.title}: {t.description or t.account}", kind="fact",
                                          proposed={"vat": proposed_vat}, amount=t.vat, txn_ids=[t.id],
                                          question=f"Record '{vat_rule.fact_needed}'. " + vat_rule.question)
                    dec = item.decision
                else:
                    dec = decision
                vo = _apply_decision_vat(dec, proposed_vat) if dec else proposed_vat
                provisional = provisional or not dec
            elif decision:
                vo = _apply_decision_vat(decision, vo)
            vat_label, vat_rec = _vat_amounts(vo, facts, t.vat)
            if facts["vat_registered"] and t.vat and vat_label in ("blocked", "partial"):
                blocked_cost = t.vat - vat_rec
                notes.append(f"£{blocked_cost / 100:,.2f} input tax not recoverable - added to the cost")

        # ---- tax amounts on the cost (including irrecoverable VAT)
        base = t.net + blocked_cost
        label, allowable, disallowed = _ct_amounts(ctx, t, facts, ct_outcome, base, calc, params_used, notes)

        # ---- overlays (pre-trading window)
        for orule, oused in overlays:
            if orule.id == "EXP-PRE-01" and facts.get("pre_trading") == "yes":
                st = ctx.client.sole_trader
                years = ctx.params.get("exp.pre_trading_years", t.date)
                params_used.append(years)
                rules_applied.append(orule.id)
                authority += [a for a in orule.authority if a not in authority]
                start = st.trading_start if st and st.trading_start else period_start
                if (start - t.date).days > int(years.value) * 365:
                    label, allowable, disallowed = "disallow", 0, base
                    notes.append(f"Incurred more than {years.value} years before trading began - not deductible")
                else:
                    notes.append(f"Pre-trading expenditure treated as incurred on {start.isoformat()}")

        out.append(Treatment(
            txn_id=t.id, date=t.date, description=t.description or t.account, category=t.category, amount=base, vat=t.vat,
            ct=label, allowable=allowable, disallowed=disallowed, vat_treatment=vat_label, vat_recoverable=vat_rec,
            rules=rules_applied, authority=authority, params=_dedupe(params_used), review_id=review_id,
            provisional=provisional, decision=decision, note="; ".join(notes),
        ))
    return out


def _dedupe(uses: List[ParamUse]) -> List[ParamUse]:
    seen, out = set(), []
    for u in uses:
        k = (u.key, u.year)
        if k not in seen:
            seen.add(k)
            out.append(u)
    return out
