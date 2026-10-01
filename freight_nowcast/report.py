"""Write the nowcast outputs: CSV panels, Markdown summary, validation, capstone feed."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping

from .engine import NowcastResult
from .feed import build_feed
from .series import add_months, month_str


def _w(path: Path, header: List[str], rows: List[Mapping[str, Any]]) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path


def _fmt(x: Any, nd: int = 2, signed: bool = True) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    if isinstance(x, (int, float)):
        return f"{x:+.{nd}f}" if signed else f"{x:.{nd}f}"
    return str(x)


def composite_rows(r: NowcastResult) -> List[Dict[str, Any]]:
    rows = []
    for m in sorted(r.composite.composite):
        row = {"month": month_str(m), "composite_z": round(r.composite.composite[m], 4),
               "phase": r.phases.get(m, ""), "coverage": round(r.composite.coverage[m], 3),
               "provisional": int(bool(r.composite.provisional.get(m)))}
        for c, g in r.geographies.items():
            row[f"{c}_z"] = round(g.composite[m], 4) if m in g.composite else ""
            row[f"{c}_phase"] = r.geo_phases[c].get(m, "")
        rows.append(row)
    return rows


def panel_rows(r: NowcastResult) -> List[Dict[str, Any]]:
    months = sorted({m for s in r.signals for m in s.monthly})
    rows = []
    for m in months:
        row: Dict[str, Any] = {"month": month_str(m)}
        for s in r.signals:
            row[f"{s.id}_level"] = round(s.monthly[m], 4) if m in s.monthly else ""
            row[f"{s.id}_momentum"] = round(s.momentum[m], 4) if m in s.momentum else ""
            row[f"{s.id}_z"] = round(s.z[m], 4) if m in s.z else ""
        rows.append(row)
    return rows


def turning_rows(r: NowcastResult) -> List[Dict[str, Any]]:
    rows = []
    for scope, g in [("GLOBAL", r.composite)] + list(r.geographies.items()):
        for t in g.turning_points:
            rows.append({"scope": scope, **t.as_row()})
    return rows


def summary_markdown(r: NowcastResult, feed: Mapping[str, Any]) -> str:
    t1 = feed["tier1"]
    lines = [f"# Freight nowcast — as of {r.as_of.isoformat()}", ""]
    if not t1.get("latest_month"):
        return "\n".join(lines + ["No composite could be built."])
    prov = " (provisional: month-to-date or incomplete coverage)" if t1["provisional"] else ""
    lines += [
        f"**Composite real-economy momentum: {t1['composite_z']:+.2f} z** in {t1['latest_month']}{prov}, "
        f"{t1['direction'] or 'n/a'} over 3 months → **{t1['phase'] or 'n/a'}** "
        f"(conviction: {t1['conviction']}).", "",
    ]
    if t1.get("turning_point"):
        tp = t1["turning_point"]
        lines += [f"⚑ Turning point: **{tp['status']} {tp['kind']}** at {tp['month']} (flagged {tp['detected']}).", ""]
    lines += ["## By geography", "", "| Geography | Month | z | 3m change | Phase | Turning point | Conviction | Coverage |",
              "|---|---|---|---|---|---|---|---|"]
    for code, g in t1["by_geography"].items():
        if not g:
            continue
        tp = g["turning_point"]
        tp_s = f"{tp['status']} {tp['kind']} {tp['month']}" if tp else ""
        lines.append(f"| {g['label']} ({code}) | {g['latest_month']}{'*' if g['provisional'] else ''} | "
                     f"{_fmt(g['composite_z'])} | {_fmt(g['change_3m'])} | {g['phase'] or '–'} | {tp_s} | "
                     f"{g['conviction']} | {g['coverage']:.0%} |")
    lines += ["", "\\* provisional", "", "## Indicators (latest)", "",
              "| Series | Geography | Mode | Last obs | Momentum | z |", "|---|---|---|---|---|---|"]
    for s in r.signals:
        m = max(s.z)
        lines.append(f"| {s.spec.get('label', s.id)} | {s.spec.get('geography')} | {s.spec.get('mode', '')} | "
                     f"{r.series_meta[s.id]['last_observation']} | {_fmt(s.momentum.get(m))} % ({s.spec.get('transform', '3m3m')}) | "
                     f"{_fmt(s.z[m])} |")
    lines += ["", "## Evidence: does each signal track what it claims to lead?", "",
              "| Indicator → target | Months | Best lead | corr | β (HAC t) | R² | OOS RMSE vs AR | DM p | Hit rate | Publication lead | Verdict |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in r.validation:
        d = p.to_dict()
        lead = f"{d['best_lead']}m" if d["best_lead"] is not None else "–"
        pub = f"{d['timing_advantage_days']} days" if d["timing_advantage_days"] is not None else "–"
        hit = "–" if d["hit_rate"] is None else f"{d['hit_rate']:.0%}"
        lines.append(
            f"| {p.indicator} → {p.target} ({p.transform}) | {p.n} | {lead} | {_fmt(d['best_corr'])} | "
            f"{_fmt(d['beta'])} ({_fmt(d['beta_t'], 1)}) | {_fmt(d['r2'], signed=False)} | "
            f"{_fmt(d['rmse_ratio'], signed=False)} | {_fmt(d['dm_p'], 3, signed=False)} | {hit} | {pub} | **{p.verdict}** |")
    notes = [f"- {p.indicator} → {p.target}: {n}" for p in r.validation for n in p.notes]
    if notes:
        lines += ["", *notes]
    lines += ["", "*Evidenced* = significant in-sample link with the expected sign **and** a better pseudo real-time "
              "nowcast than the target's own lag (RMSE ratio < 1, Diebold-Mariano p < 0.10).", ""]
    turns = [t for t in r.composite.turning_points if t.kind in ("peak", "trough")][-6:]
    if turns:
        lines += ["## Recent composite turning points", "", "| Month | Kind | Status | z | Flagged |", "|---|---|---|---|---|"]
        lines += [f"| {month_str(t.month)} | {t.kind} | {t.status} | {t.value:+.2f} | {month_str(t.detected)} |" for t in turns]
        lines.append("")
    t2 = feed["tier2"]
    if t2["tilt"]["sectors"]:
        lines += ["## Tier 2 cycle / sector tilt", "",
                  f"Phase **{t2['cycle_phase']}**, conviction {t2['conviction']}; cyclicals minus defensives "
                  f"{_fmt(t2['tilt']['cyclical_minus_defensive'])}.", "",
                  "| Sector | Tilt |", "|---|---|"]
        lines += [f"| {k.replace('_', ' ')} | {v:+.2f} |" for k, v in
                  sorted(t2["tilt"]["sectors"].items(), key=lambda kv: -kv[1])]
        lines.append("")
    if r.warnings:
        lines += ["## Data warnings", ""] + [f"- {w}" for w in r.warnings] + [""]
    return "\n".join(lines)


def write_outputs(r: NowcastResult, cfg: Mapping[str, Any], out_dir: Path) -> Dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    feed = build_feed(r, cfg)
    comp = composite_rows(r)
    panel = panel_rows(r)
    paths = {
        "composite": _w(out_dir / "composite.csv", list(comp[0].keys()) if comp else ["month"], comp),
        "panel": _w(out_dir / "indicator_panel.csv", list(panel[0].keys()) if panel else ["month"], panel),
        "turning_points": _w(out_dir / "turning_points.csv",
                             ["scope", "month", "kind", "status", "value", "detected"], turning_rows(r)),
    }
    (out_dir / "validation.json").write_text(json.dumps([p.to_dict() for p in r.validation], indent=2), encoding="utf-8")
    paths["validation"] = out_dir / "validation.json"
    (out_dir / "capstone_feed.json").write_text(json.dumps(feed, indent=2), encoding="utf-8")
    paths["capstone_feed"] = out_dir / "capstone_feed.json"
    (out_dir / "nowcast_summary.md").write_text(summary_markdown(r, feed), encoding="utf-8")
    paths["summary"] = out_dir / "nowcast_summary.md"
    return paths
