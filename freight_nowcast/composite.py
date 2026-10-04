"""Per-series z-scores, per-geography composites and the cycle phase."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Mapping, Optional

from .series import Month, Monthly, Series, add_months, rolling_zscore, transform
from .turning import TurningPoint, turning_points

PHASES = {  # (level >= 0, rising) -> phase
    (False, True): "Recovery",
    (True, True): "Expansion",
    (True, False): "Slowdown",
    (False, False): "Contraction",
}


@dataclass
class IndicatorSignal:
    spec: Mapping[str, Any]
    monthly: Monthly
    coverage: Dict[Month, float]
    momentum: Monthly
    z: Monthly

    @property
    def id(self) -> str:
        return self.spec["id"]


@dataclass
class GeoComposite:
    code: str
    label: str
    weight: float
    composite: Monthly
    coverage: Dict[Month, float]          # share of indicator weight present
    provisional: Dict[Month, bool]        # built on month-to-date data or incomplete coverage
    members: List[str]
    turning_points: List[TurningPoint] = field(default_factory=list)


def build_signal(series: Series, spec: Mapping[str, Any], zcfg: Mapping[str, Any], as_of: Optional[date]) -> IndicatorSignal:
    monthly, coverage = series.to_monthly(as_of, spec.get("min_month_coverage", 0.25))
    mom = transform(monthly, spec.get("transform", "3m3m"))
    z = rolling_zscore(mom, zcfg.get("window", 60), zcfg.get("min_periods", 24), zcfg.get("clip", 4.0))
    sign = float(spec.get("sign", 1))
    return IndicatorSignal(spec, monthly, coverage, mom, {m: sign * v for m, v in z.items()})


def _weighted(signals: List[IndicatorSignal], weights: Mapping[str, float], min_coverage: float):
    months = sorted({m for s in signals for m in s.z})
    total = sum(weights[s.id] for s in signals) or 1.0
    comp, cov, prov = {}, {}, {}
    for m in months:
        got = [(s, weights[s.id]) for s in signals if m in s.z]
        w = sum(wt for _, wt in got)
        if not got or w / total < min_coverage:
            continue
        comp[m] = sum(s.z[m] * wt for s, wt in got) / w
        cov[m] = w / total
        # provisional = built on month-to-date data, or a member has history but has
        # not published this month yet (ragged edge); a member whose history starts
        # later does not make old months provisional
        not_yet = any(m not in s.z and s.z and min(s.z) < m for s in signals)
        prov[m] = not_yet or any(s.coverage.get(m, 1.0) < 1.0 for s, _ in got)
    return comp, cov, prov


def build_geographies(signals: List[IndicatorSignal], geos: Mapping[str, Mapping[str, Any]],
                      min_coverage: float = 0.5, tp_cfg: Optional[Dict] = None) -> Dict[str, GeoComposite]:
    out = {}
    for code, g in geos.items():
        members = [s for s in signals if s.spec.get("geography") == code]
        if not members:
            continue
        weights = {s.id: float(s.spec.get("weight", 1.0)) for s in members}
        comp, cov, prov = _weighted(members, weights, min_coverage)
        gc = GeoComposite(code, g.get("label", code), float(g.get("weight", 1.0)), comp, cov, prov,
                          [s.id for s in members])
        gc.turning_points = turning_points(comp, tp_cfg)
        out[code] = gc
    return out


def build_global(geos: Mapping[str, GeoComposite], min_coverage: float = 0.5,
                 tp_cfg: Optional[Dict] = None) -> GeoComposite:
    months = sorted({m for g in geos.values() for m in g.composite})
    total = sum(g.weight for g in geos.values()) or 1.0
    comp, cov, prov = {}, {}, {}
    for m in months:
        got = [g for g in geos.values() if m in g.composite]
        w = sum(g.weight for g in got)
        if not got or w / total < min_coverage:
            continue
        comp[m] = sum(g.composite[m] * g.weight for g in got) / w
        cov[m] = w / total
        not_yet = any(m not in g.composite and g.composite and min(g.composite) < m for g in geos.values())
        prov[m] = not_yet or any(g.provisional.get(m) for g in got)
    gc = GeoComposite("GLOBAL", "Composite", 1.0, comp, cov, prov, list(geos))
    gc.turning_points = turning_points(comp, tp_cfg)
    return gc


def phase(x: Monthly, month: Month, horizon: int = 3) -> Optional[str]:
    """Cycle-clock phase: level above/below trend (z vs 0) x direction over ``horizon`` months."""
    if month not in x:
        return None
    prev = x.get(add_months(month, -horizon))
    if prev is None:
        return None
    return PHASES[(x[month] >= 0, x[month] > prev)]


def phase_history(x: Monthly, horizon: int = 3) -> Dict[Month, str]:
    return {m: p for m in sorted(x) if (p := phase(x, m, horizon))}
