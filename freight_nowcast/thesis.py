"""An automatically written thesis: what the latest freight data could mean for the global economy.

The dashboard republishes itself whenever new data lands, so a hand-written
commentary would go stale. This module rewrites it from the numbers on every
run with fixed, inspectable rules:

- the overall direction (composite level, momentum, phase)
- where regions diverge
- freight *costs* against freight *volumes* (demand-led vs supply-squeezed)
- chokepoint shocks (Strait of Hormuz, Bab el-Mandeb) with when they began
- implications for growth, inflation, trade and positioning
- what would confirm or overturn the read, and how much evidence backs it

It describes what the data is consistent with. It is not a forecast and not
investment advice, and every number in it traces back to the outputs.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from .composite import IndicatorSignal
from .engine import NowcastResult
from .series import Month, add_months, month_str

_MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August",
                "September", "October", "November", "December"]

HEADLINES = {
    "Expansion": "the global goods economy is running above trend and still gaining pace",
    "Slowdown": "the global goods economy is above trend but losing momentum",
    "Contraction": "the global goods economy is running below trend and weakening",
    "Recovery": "the global goods economy is below trend but turning up",
}


def _mname(m: Month) -> str:
    return f"{_MONTH_NAMES[m[1] - 1]} {m[0]}"


def _pct(x: float) -> str:
    return f"{x:+.0f}%" if abs(x) >= 10 else f"{x:+.1f}%"


def _latest(sig: IndicatorSignal) -> Optional[Month]:
    return max(sig.z) if sig.z else None


def _by_kind(r: NowcastResult, kind: str) -> List[IndicatorSignal]:
    return [s for s in r.signals if s.spec.get("kind") == kind and s.z]


def _shock(sig: IndicatorSignal, threshold: float) -> Optional[Dict[str, Any]]:
    """A sustained collapse: latest y/y change below ``threshold``; when it began and how deep."""
    m = _latest(sig)
    if m is None or sig.momentum.get(m) is None or sig.momentum[m] > threshold:
        return None
    start = m
    while add_months(start, -1) in sig.momentum and sig.momentum[add_months(start, -1)] <= threshold:
        start = add_months(start, -1)
    before = [sig.monthly[x] for x in (add_months(start, -k) for k in (1, 2, 3)) if x in sig.monthly]
    after = sig.monthly.get(m)
    level_drop = (after / (sum(before) / len(before)) - 1) * 100 if before and after is not None else None
    months = (m[0] - start[0]) * 12 + m[1] - start[1] + 1
    return {"since": start, "months": months, "yoy": sig.momentum[m], "level_drop": level_drop, "latest": m}


def build_thesis(r: NowcastResult, feed: Mapping[str, Any]) -> Dict[str, Any]:
    t1, t2 = feed["tier1"], feed["tier2"]
    if not t1.get("latest_month"):
        return {"headline": "Not enough data for a read yet.", "sections": [], "implications": [], "watch": []}
    z, phase, direction = t1["composite_z"], t1["phase"], t1.get("direction")
    sections: List[Dict[str, str]] = []
    implications: List[str] = []
    watch: List[str] = []

    # 1. Direction --------------------------------------------------------------
    headline = (f"Freight data says {HEADLINES.get(phase, 'the picture is unclear')} "
                f"(composite {z:+.2f} z, {direction or 'flat'} over three months).")

    # 2. Regions ----------------------------------------------------------------
    geos = [(c, g) for c, g in t1["by_geography"].items() if g and g.get("composite_z") is not None]
    if geos:
        geos.sort(key=lambda cg: cg[1]["composite_z"], reverse=True)
        (hc, hi), (lc, lo) = geos[0], geos[-1]
        spread = hi["composite_z"] - lo["composite_z"]
        parts = [f"{g['label']} {g['composite_z']:+.1f} z ({(g['phase'] or 'n/a').lower()})" for _, g in geos]
        if spread >= 1.5:
            text = (f"The world is moving at different speeds. {hi['label']} is the strongest "
                    f"({hi['composite_z']:+.1f} z) and {lo['label']} the weakest ({lo['composite_z']:+.1f} z), "
                    f"a gap of {spread:.1f} standard deviations. ")
            implications.append(f"Growth is uneven: activity tied to {hi['label']} should keep outperforming "
                                f"activity tied to {lo['label']} while the gap persists.")
        elif spread >= 0.75:
            text = (f"Regions are diverging: {hi['label']} ({hi['composite_z']:+.1f} z) is running ahead of "
                    f"{lo['label']} ({lo['composite_z']:+.1f} z). ")
        else:
            text = "Regions are moving broadly together. "
        sections.append({"title": "Where", "text": text + "By region: " + "; ".join(parts) + "."})

    # 3. Freight costs vs volumes ----------------------------------------------------
    rates, vols = _by_kind(r, "freight_rate"), _by_kind(r, "global_volume")
    if rates and vols:
        rz = rates[0].z[_latest(rates[0])]
        vz = vols[0].z[_latest(vols[0])]
        rm = rates[0].momentum.get(_latest(rates[0]))
        vm = vols[0].momentum.get(_latest(vols[0]))
        rl, vl = rates[0].spec.get("label"), vols[0].spec.get("label")
        if rz > 0.5 and vz < -0.5:
            text = (f"Shipping is getting dearer while less cargo moves: {rl} {_pct(rm)} y/y ({rz:+.1f} z) "
                    f"against {vl} {_pct(vm)} y/y ({vz:+.1f} z). Rising rates on falling volumes point to a "
                    f"supply squeeze (lost capacity, rerouting, longer voyages), not a demand boom.")
            implications.append("Cost-push pressure on traded goods: higher freight costs feed into import "
                                "prices and goods inflation with a lag of a few months, while real trade volumes soften.")
        elif rz > 0.5 and vz > 0.5:
            text = f"Freight rates ({_pct(rm)} y/y) and volumes ({_pct(vm)} y/y) are rising together: a demand-led upswing."
            implications.append("Demand-led goods cycle: supportive for industrial output and trade, "
                                "with some upward pressure on goods prices.")
        elif rz < -0.5 and vz < -0.5:
            text = f"Freight rates ({_pct(rm)} y/y) and volumes ({_pct(vm)} y/y) are falling together: demand is weakening."
            implications.append("Disinflationary for goods: weak demand is pulling freight costs and volumes down.")
        else:
            text = (f"Freight rates ({_pct(rm)} y/y) and volumes ({_pct(vm)} y/y) send no strong joint signal.")
        sections.append({"title": "Costs vs volumes", "text": text})

    # 4. Chokepoints --------------------------------------------------------------
    shock_texts = []
    for sig in _by_kind(r, "chokepoint"):
        s = _shock(sig, -40.0)
        name = sig.spec.get("label", sig.id).replace(" transits (IMF PortWatch)", "")
        note = sig.spec.get("chokepoint_note", "")
        if s:
            depth = f"{s['level_drop']:+.0f}% against the three months before" if s["level_drop"] is not None else ""
            shock_texts.append(
                f"Traffic through the {name} is down {abs(s['yoy']):.0f}% on a year ago ({depth}). The fall began in "
                f"{_mname(s['since'])} and has lasted {s['months']} month{'s' if s['months'] != 1 else ''}. "
                + (f"The {name} {note}. " if note else ""))
            if sig.spec.get("chokepoint_energy"):
                implications.append(f"Energy supply risk: a sustained {name} disruption tightens oil and LNG supply, "
                                    "raising energy prices and the inflation outlook for importers (Europe and Asia most exposed), "
                                    "while cutting Gulf export volumes.")
            else:
                implications.append(f"Longer routes: diversions away from the {name} add sailing days and cost, "
                                    "keeping freight rates elevated.")
            watch.append(f"{name} transits: a recovery towards pre-{_MONTH_NAMES[s['since'][1] - 1]} levels would ease "
                         "the energy and freight-cost pressure.")
        else:
            m = _latest(sig)
            mom = sig.momentum.get(m) if m else None
            if mom is not None and mom <= -15:
                shock_texts.append(f"{name} transits are down {abs(mom):.0f}% y/y. ")
    if shock_texts:
        sections.append({"title": "Chokepoints", "text": "".join(shock_texts).strip()})

    # 5. Phase-level implications ----------------------------------------------------
    phase_impl = {
        "Expansion": "Growth: manufacturing and trade are likely to keep expanding near term; watch for capacity constraints.",
        "Slowdown": "Growth: momentum is fading; official production and trade data are likely to soften in coming releases.",
        "Contraction": "Growth: a goods-sector downturn; official production and trade data are likely to print weak in coming releases.",
        "Recovery": "Growth: the trough may be behind us; official production and trade data should start to improve if the turn holds.",
    }
    if phase in phase_impl:
        implications.insert(0, phase_impl[phase])
    energy_shock = any(s.spec.get("chokepoint_energy") and _shock(s, -40.0) for s in _by_kind(r, "chokepoint"))
    if phase in ("Recovery", "Expansion") and energy_shock:
        implications.insert(1, "The upturn is fragile: it is running alongside an energy-route shock. If higher "
                               "energy and freight costs feed through, the recovery could stall before official data confirms it.")
    tilt = (t2.get("tilt") or {}).get("cyclical_minus_defensive")
    if tilt is not None:
        side = "cyclicals over defensives" if tilt > 0 else "defensives over cyclicals"
        implications.append(f"Positioning: the cycle phase favours {side} (tilt {tilt:+.2f}, scaled by "
                            f"{t2.get('conviction')} conviction).")

    # 6. What to watch ------------------------------------------------------------
    tp = t1.get("turning_point")
    if tp:
        tm = (int(tp["month"][:4]), int(tp["month"][5:7]))
        watch.insert(0, f"The {tp['status']} {tp['kind']} in {_mname(tm)}: a move of 0.5 z the other way sustained "
                        "for two months would flag a new turn.")
    else:
        watch.insert(0, "No turning point in the last six months; a 0.5 z move off the recent extreme sustained for "
                        "two months would flag one.")
    targets = [m for m in r.series_meta.values() if m["role"] == "target" and m.get("last_observation")]
    if targets:
        oldest = min(targets, key=lambda m: m["last_observation"])
        om = (int(oldest["last_observation"][:4]), int(oldest["last_observation"][5:7]))
        watch.append(f"Official data lags the freight data: {oldest['label']} is only available to {_mname(om)}. "
                     "The next official releases will confirm or contradict this read.")

    # 7. Confidence -------------------------------------------------------------
    ev = [p for p in r.validation if p.verdict not in ("not run", "insufficient data")]
    good = [p for p in ev if p.verdict == "evidenced"]
    confidence = (f"Conviction is {t1['conviction']}. {len(good)} of {len(ev)} indicator-to-official-data links pass the "
                  f"out-of-sample evidence test"
                  + (" and the latest month is provisional (month-to-date data)" if t1.get("provisional") else "")
                  + ". Treat this as a hypothesis the next official releases will test.")
    return {"headline": headline, "sections": sections, "implications": implications, "watch": watch,
            "confidence": confidence,
            "method": "Written automatically from the latest data by fixed rules on every run. It describes what "
                      "the freight data is consistent with; it is not a forecast or investment advice."}


def thesis_markdown(th: Mapping[str, Any]) -> List[str]:
    lines = ["## What this could mean for the global economy", "", f"**{th['headline']}**", ""]
    for s in th.get("sections", []):
        lines += [f"**{s['title']}.** {s['text']}", ""]
    if th.get("implications"):
        lines += ["Implications:", ""] + [f"- {x}" for x in th["implications"]] + [""]
    if th.get("watch"):
        lines += ["What to watch:", ""] + [f"- {x}" for x in th["watch"]] + [""]
    if th.get("confidence"):
        lines += [f"*{th['confidence']}*", ""]
    if th.get("method"):
        lines += [f"<sub>{th['method']}</sub>", ""]
    return lines
