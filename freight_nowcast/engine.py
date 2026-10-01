"""The nowcast pipeline: cached series -> signals -> composites -> phases, turns, evidence."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .catalog import enabled_series, specs_by_id
from .composite import GeoComposite, IndicatorSignal, build_geographies, build_global, build_signal, phase_history
from .series import Month, Monthly, Series
from .sources import SourceError, read_cache
from .validation import PairResult, run_validation


@dataclass
class NowcastResult:
    as_of: date
    signals: List[IndicatorSignal]
    monthly: Dict[str, Monthly]
    geographies: Dict[str, GeoComposite]
    composite: GeoComposite
    phases: Dict[Month, str]
    geo_phases: Dict[str, Dict[Month, str]]
    validation: List[PairResult]
    series_meta: Dict[str, Dict[str, Any]]
    warnings: List[str] = field(default_factory=list)
    data_mode: str = "live"                      # live | synthetic
    manifest: Dict[str, Any] = field(default_factory=dict)


def load_series(cfg: Mapping[str, Any], cache_dir: Path) -> Tuple[Dict[str, Series], List[str]]:
    loaded, warnings = {}, []
    for spec in enabled_series(cfg):
        try:
            loaded[spec["id"]] = read_cache(cache_dir, spec["id"], spec.get("frequency", "M"), spec.get("source", ""))
        except SourceError as exc:
            if spec.get("optional"):
                warnings.append(f"{spec['id']}: optional, no data cached yet (skipped)")
            else:
                warnings.append(f"MISSING {exc}")
    if (Path(cache_dir) / "_SYNTHETIC_DEMO_DATA").exists():
        warnings.insert(0, "SYNTHETIC DEMO DATA: these outputs are not real statistics")
    return loaded, warnings


def splice_extensions(series: Dict[str, Series], specs: Mapping[str, Mapping[str, Any]], as_of: Optional[date],
                      warnings: List[str]) -> Dict[str, Series]:
    """Extend a monthly series with a higher-frequency sibling at the ragged edge.

    A spec with ``"extends": "<parent id>"`` (the working-daily toll index for the
    monthly one) contributes only the months *after* the parent's last published
    month. Its month(-to-date) averages are rebased onto the parent's level using
    the median ratio over the last 12 overlapping months, so a partial month
    becomes a provisional reading of the parent rather than a separate signal.
    """
    out = dict(series)
    for sid, spec in specs.items():
        parent_id = spec.get("extends")
        if not parent_id or sid not in series or parent_id not in series:
            continue
        child, parent = series[sid], series[parent_id]
        cm, ccov = child.to_monthly(as_of, spec.get("min_month_coverage", 0.25))
        pm, _ = parent.to_monthly(as_of)
        overlap = sorted(set(cm) & set(pm))[-12:]
        if len(overlap) < 3:
            warnings.append(f"{sid}: fewer than 3 months overlap with {parent_id}; not spliced")
            continue
        ratios = sorted(pm[m] / cm[m] for m in overlap if cm[m])
        k = ratios[len(ratios) // 2]
        last = max(pm)
        extra = [(date(m[0], m[1], 1), cm[m] * k) for m in sorted(cm) if m > last]
        if not extra:
            continue
        spliced = Series(parent_id, parent.observations + extra, "M", parent.source, dict(parent.meta))
        partial = {(d.year, d.month): ccov[(d.year, d.month)] for d, _ in extra}
        spliced.meta["extended_by"] = sid
        spliced.meta["extended_to"] = child.last_date.isoformat()
        out[parent_id] = _WithCoverage(spliced, partial)
    return out


class _WithCoverage(Series):
    """A spliced monthly series that remembers which months are month-to-date."""

    def __init__(self, base: Series, partial: Dict[Month, float]):
        super().__init__(base.id, base.observations, base.frequency, base.source, base.meta)
        self.partial = partial

    def to_monthly(self, as_of=None, min_coverage=0.0):
        vals, cov = super().to_monthly(as_of, min_coverage)
        for m, c in self.partial.items():
            if m in cov:
                cov[m] = c
        return vals, cov


def run(cfg: Mapping[str, Any], cache_dir: Path, as_of: Optional[date] = None,
        series: Optional[Dict[str, Series]] = None) -> NowcastResult:
    as_of = as_of or date.today()
    warnings: List[str] = []
    synthetic = (Path(cache_dir) / "_SYNTHETIC_DEMO_DATA").exists()
    manifest: Dict[str, Any] = {}
    if not synthetic and (Path(cache_dir) / "_manifest.json").exists():
        from .live import read_manifest
        manifest = read_manifest(cache_dir)
        for sid, e in manifest.get("series", {}).items():
            if e.get("status") == "failed" and sid in {s["id"] for s in enabled_series(cfg)}:
                kept = f"; using cache from {e['last_good_fetch']}" if e.get("last_good_fetch") else ""
                warnings.append(f"{sid}: last fetch failed ({e.get('error', '')[:160]}){kept}")
    if series is None:
        series, warnings = load_series(cfg, cache_dir)
    specs = specs_by_id(cfg)
    zcfg = cfg.get("zscore", {})
    tp_cfg = cfg.get("turning_points", {})
    min_cov = cfg.get("composite", {}).get("min_coverage", 0.5)

    series = splice_extensions(series, specs, as_of, warnings)
    signals, monthly, meta = [], {}, {}
    for sid, s in series.items():
        spec = specs.get(sid)
        if spec is None or spec.get("extends"):
            continue
        m, cov = s.to_monthly(as_of, spec.get("min_month_coverage", 0.25))
        monthly[sid] = m
        meta[sid] = {"label": spec.get("label", sid), "role": spec["role"], "mode": spec.get("mode", ""),
                     "geography": spec.get("geography", ""), "source": s.source,
                     "last_observation": s.meta.get("extended_to") or (s.last_date.isoformat() if s.last_date else None),
                     "extended_by": s.meta.get("extended_by"),
                     "latest_month_coverage": cov[max(cov)] if cov else None,
                     "fetched_at": manifest.get("series", {}).get(sid, {}).get("fetched_at")
                     or manifest.get("series", {}).get(sid, {}).get("last_good_fetch")}
        if spec["role"] == "indicator":
            sig = build_signal(s, spec, zcfg, as_of)
            if not sig.z:
                warnings.append(f"{sid}: too short for a z-score (need {zcfg.get('min_periods', 24)} months of momentum)")
                continue
            signals.append(sig)
    if not signals:
        raise SourceError("no indicator series with enough history; fetch data or run `freight-nowcast demo`")

    geos = build_geographies(signals, cfg["geographies"], min_cov, tp_cfg)
    comp = build_global(geos, min_cov, tp_cfg)
    horizon = cfg.get("composite", {}).get("phase_horizon", 3)
    return NowcastResult(
        as_of=as_of, signals=signals, monthly=monthly, geographies=geos, composite=comp,
        phases=phase_history(comp.composite, horizon),
        geo_phases={c: phase_history(g.composite, horizon) for c, g in geos.items()},
        validation=run_validation(cfg.get("validation", []), monthly, specs),
        series_meta=meta, warnings=warnings,
        data_mode="synthetic" if synthetic else "live", manifest=manifest,
    )
