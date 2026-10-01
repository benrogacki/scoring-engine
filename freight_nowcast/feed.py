"""The capstone contract: what the freight nowcaster hands to Tier 1 and Tier 2.

Tier 1 reads the *real-economy* line (composite z, phase, turning point, how well
evidenced it is) next to the yield curve. Tier 2 turns the cycle phase into a
cycle/sector tilt, scaled by conviction. The schema is versioned so the capstone
can reject a feed it does not understand.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from .composite import GeoComposite
from .engine import NowcastResult
from .series import Month, add_months, month_str
from .turning import TurningPoint

SCHEMA = "freight_nowcast/capstone_feed@1"

DEFAULT_TILTS = {
    # -1 underweight .. +1 overweight, before conviction scaling
    "Recovery":    {"industrials": 1.0, "materials": 1.0, "transport_logistics": 1.0, "consumer_discretionary": 1.0,
                    "financials": 0.5, "technology": 0.5, "energy": 0.0,
                    "healthcare": -0.5, "consumer_staples": -1.0, "utilities": -1.0},
    "Expansion":   {"industrials": 0.5, "materials": 0.5, "transport_logistics": 0.5, "consumer_discretionary": 0.5,
                    "financials": 0.5, "technology": 0.5, "energy": 1.0,
                    "healthcare": -0.5, "consumer_staples": -0.5, "utilities": -0.5},
    "Slowdown":    {"industrials": -0.5, "materials": -0.5, "transport_logistics": -1.0, "consumer_discretionary": -0.5,
                    "financials": -0.5, "technology": 0.0, "energy": 0.5,
                    "healthcare": 1.0, "consumer_staples": 0.5, "utilities": 0.5},
    "Contraction": {"industrials": -1.0, "materials": -1.0, "transport_logistics": -1.0, "consumer_discretionary": -1.0,
                    "financials": -0.5, "technology": -0.5, "energy": -0.5,
                    "healthcare": 1.0, "consumer_staples": 1.0, "utilities": 1.0},
}
CYCLICALS = ("industrials", "materials", "transport_logistics", "consumer_discretionary")
DEFENSIVES = ("healthcare", "consumer_staples", "utilities")
CONVICTION_SCALE = {"high": 1.0, "medium": 2 / 3, "low": 1 / 3}


def _r(x: Optional[float], nd: int = 3) -> Optional[float]:
    return None if x is None else round(x, nd)


def latest_turn(g: GeoComposite, latest: Month, within: int = 6) -> Optional[Dict[str, Any]]:
    """The most recent peak/trough flagged within ``within`` months of the latest reading."""
    turns = [t for t in g.turning_points if t.kind in ("peak", "trough")]
    if not turns:
        return None
    t = turns[-1]
    if t.detected < add_months(latest, -within):
        return None
    return t.as_row()


def evidence_for(result: NowcastResult, members: List[str]) -> Dict[str, str]:
    return {f"{p.indicator}->{p.target}": p.verdict for p in result.validation if p.indicator in members}


def evidenced_share(result: NowcastResult, members: List[str]) -> float:
    """Share of the members' composite weight carried by indicators with an *evidenced* pair."""
    ok = {p.indicator for p in result.validation if p.verdict == "evidenced"}
    weights = {s.id: float(s.spec.get("weight", 1.0)) for s in result.signals if s.id in members}
    total = sum(weights.values())
    return sum(w for sid, w in weights.items() if sid in ok) / total if total else 0.0


def conviction(z: float, provisional: bool, evidenced: float) -> str:
    """high/medium/low from the size of the move, less a notch each for a provisional
    reading and for resting mostly (< 50% of weight) on unevidenced indicators."""
    level = 2 if abs(z) >= 1.0 else 1 if abs(z) >= 0.5 else 0
    if provisional:
        level -= 1
    if evidenced < 0.5:
        level -= 1
    return ["low", "medium", "high"][max(0, min(2, level))]


def _read(result: NowcastResult, g: GeoComposite, phases: Mapping[Month, str]) -> Optional[Dict[str, Any]]:
    if not g.composite:
        return None
    latest = max(g.composite)
    z = g.composite[latest]
    prev = g.composite.get(add_months(latest, -3))
    members = g.members if g.code != "GLOBAL" else [m for c in g.members for m in result.geographies[c].members]
    ev = evidence_for(result, members)
    share = evidenced_share(result, members)
    return {
        "label": g.label,
        "latest_month": month_str(latest),
        "composite_z": _r(z),
        "change_3m": _r(z - prev) if prev is not None else None,
        "direction": None if prev is None else ("rising" if z > prev else "falling"),
        "phase": phases.get(latest),
        "provisional": bool(g.provisional.get(latest)),
        "coverage": _r(g.coverage.get(latest), 2),
        "turning_point": latest_turn(g, latest),
        "evidence": ev,
        "evidenced_weight_share": _r(share, 2),
        "conviction": conviction(z, bool(g.provisional.get(latest)), share),
    }


def tilt(phase: Optional[str], conv: str, table: Mapping[str, Mapping[str, float]]) -> Dict[str, Any]:
    if phase not in table:
        return {"sectors": {}, "cyclical_minus_defensive": None}
    k = CONVICTION_SCALE[conv]
    sectors = {s: round(v * k, 2) for s, v in table[phase].items()}
    cyc = [sectors[s] for s in CYCLICALS if s in sectors]
    dfn = [sectors[s] for s in DEFENSIVES if s in sectors]
    spread = (sum(cyc) / len(cyc) - sum(dfn) / len(dfn)) if cyc and dfn else None
    return {"sectors": sectors, "cyclical_minus_defensive": _r(spread, 2)}


def build_feed(result: NowcastResult, cfg: Mapping[str, Any]) -> Dict[str, Any]:
    table = cfg.get("tier2_tilts") or DEFAULT_TILTS
    top = _read(result, result.composite, result.phases)
    by_geo = {c: _read(result, g, result.geo_phases[c]) for c, g in result.geographies.items()}
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "as_of": result.as_of.isoformat(),
        "data_mode": result.data_mode,
        "data_updated_at": result.manifest.get("updated_at"),
        "tier1": {
            "signal": "real_economy_momentum",
            "read_alongside": "yield_curve",
            "units": "z-score of freight momentum vs trailing history; 0 = normal pace",
            **(top or {}),
            "by_geography": by_geo,
        },
        "tier2": {
            "cycle_phase": top and top["phase"],
            "conviction": top and top["conviction"],
            "tilt": tilt(top and top["phase"], top["conviction"] if top else "low", table),
            "by_geography": {c: {"phase": r["phase"], "conviction": r["conviction"],
                                 "tilt": tilt(r["phase"], r["conviction"], table)}
                             for c, r in by_geo.items() if r},
            "note": "Directional tilts in [-1, 1] scaled by conviction; the capstone sizes them.",
        },
        "validation": [p.to_dict() for p in result.validation],
        "series": result.series_meta,
        "warnings": result.warnings,
    }
