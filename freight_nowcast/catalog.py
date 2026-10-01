"""The series catalog: what to fetch, how to transform it, where it counts."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent.parent / "config" / "freight_nowcast.json"
TRANSFORMS = {"mom", "yoy", "3m3m", "diff", "level"}
FREQUENCIES = {"D", "W", "M"}
ROLES = {"indicator", "target"}


class CatalogError(ValueError):
    pass


def load_catalog(path: Optional[Path] = None) -> Dict[str, Any]:
    path = Path(path) if path else DEFAULT_CATALOG_PATH
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg["_base_dir"] = str(path.resolve().parent.parent if path.parent.name == "config" else path.resolve().parent)
    check_catalog(cfg)
    return cfg


def check_catalog(cfg: Dict[str, Any]) -> None:
    series = cfg.get("series") or []
    ids = [s.get("id") for s in series]
    errors: List[str] = []
    if len(set(ids)) != len(ids) or None in ids:
        errors.append("every series needs a unique id")
    geos = cfg.get("geographies") or {}
    for s in series:
        sid = s.get("id")
        if s.get("role") not in ROLES:
            errors.append(f"{sid}: role must be one of {sorted(ROLES)}")
        if s.get("frequency", "M") not in FREQUENCIES:
            errors.append(f"{sid}: frequency must be one of {sorted(FREQUENCIES)}")
        if s.get("transform", "3m3m") not in TRANSFORMS:
            errors.append(f"{sid}: transform must be one of {sorted(TRANSFORMS)}")
        if s.get("role") == "indicator" and s.get("geography") not in geos:
            errors.append(f"{sid}: geography {s.get('geography')!r} is not in geographies")
        if s.get("source") not in {"genesis", "sdmx", "csv"}:
            errors.append(f"{sid}: source must be genesis, sdmx or csv")
    for p in cfg.get("validation") or []:
        for k in ("indicator", "target"):
            if p.get(k) not in ids:
                errors.append(f"validation pair refers to unknown series {p.get(k)!r}")
        if p.get("transform", "mom") not in TRANSFORMS:
            errors.append(f"validation {p.get('indicator')}: bad transform")
    if errors:
        raise CatalogError("; ".join(errors))


def specs_by_id(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {s["id"]: copy.deepcopy(s) for s in cfg.get("series", [])}
