"""Self-contained HTML dashboard for a nowcast run (open in any browser, no install)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping

from .catalog import enabled_series
from .engine import NowcastResult
from .feed import build_feed
from .series import month_str

TEMPLATE = Path(__file__).with_name("templates") / "dashboard.html"


def source_status(r: NowcastResult, cfg: Mapping[str, Any]) -> list:
    """One row per enabled catalog series: did it arrive, from where, and what to do if not."""
    entries = r.manifest.get("series", {})
    rows = []
    for spec in enabled_series(cfg):
        sid = spec["id"]
        e = entries.get(sid, {})
        meta = r.series_meta.get(sid, {})
        spliced = any(m.get("extended_by") == sid for m in r.series_meta.values())
        if r.data_mode == "synthetic":
            status = "synthetic" if sid in r.series_meta or spliced else "absent"
        elif e.get("status") == "ok":
            status = "fallback" if (e.get("details") or {}).get("fallback_used") else "ok"
        elif e.get("status") == "failed":
            status = "stale" if e.get("last_good_fetch") else "missing"
        else:
            status = "ok" if sid in r.series_meta else "missing"
        note = ""
        if status == "fallback":
            note = "Primary failed; using fallback " + (e.get("details") or {}).get("fallback_used", "")[:140]
        elif status in ("stale", "missing"):
            note = (e.get("error") or "")[:220]
            if spec.get("how_to_get"):
                note += " | " + spec["how_to_get"]
        rows.append({"id": sid, "label": spec.get("label", sid), "role": spec.get("role"),
                     "geo": spec.get("geography", ""), "status": status,
                     "required": not spec.get("optional"),
                     "last": meta.get("last_observation") or e.get("last"),
                     "origin": "synthetic" if r.data_mode == "synthetic" else
                     (meta.get("source") or e.get("origin") or spec.get("source")),
                     "fetched": e.get("fetched_at") or e.get("last_good_fetch"), "note": note})
    return rows


def payload(r: NowcastResult, cfg: Mapping[str, Any]) -> Dict[str, Any]:
    def line(x, prov):
        return [[month_str(m), round(v, 3), int(bool(prov.get(m)))] for m, v in sorted(x.items())]

    feed = build_feed(r, cfg)
    return {
        "as_of": r.as_of.isoformat(),
        "synthetic": r.data_mode == "synthetic",
        "data_updated_at": r.manifest.get("updated_at"),
        "vintages": [{"id": sid, "label": m["label"], "role": m["role"], "last": m["last_observation"],
                      "fetched": m.get("fetched_at"), "origin": m["source"]}
                     for sid, m in r.series_meta.items()],
        "composite": line(r.composite.composite, r.composite.provisional),
        "phases": {month_str(m): p for m, p in r.phases.items()},
        "turns": [t.as_row() for t in r.composite.turning_points if t.kind in ("peak", "trough")],
        "geos": [{"code": c, "label": g.label, "line": line(g.composite, g.provisional),
                  "turns": [t.as_row() for t in g.turning_points if t.kind in ("peak", "trough")]}
                 for c, g in r.geographies.items()],
        "indicators": [{"id": s.id, "label": s.spec.get("label", s.id), "geo": s.spec.get("geography"),
                        "mode": s.spec.get("mode", ""), "transform": s.spec.get("transform", "3m3m"),
                        "last": r.series_meta[s.id]["last_observation"],
                        "z": round(s.z[max(s.z)], 2), "momentum": round(s.momentum[max(s.z)], 2),
                        "line": [[month_str(m), round(v, 3), int(s.coverage.get(m, 1.0) < 1.0)]
                                 for m, v in sorted(s.z.items())]}
                       for s in r.signals],
        "validation": [p.to_dict() for p in r.validation],
        "feed": feed,
        "warnings": r.warnings,
        "sources": source_status(r, cfg),
    }


def write_dashboard(r: NowcastResult, cfg: Mapping[str, Any], path: Path) -> Path:
    data = json.dumps(payload(r, cfg)).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", data)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(html, encoding="utf-8")
    return Path(path)
