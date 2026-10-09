"""Year-versioned tax parameters.

Each ``<tax-year>.json`` file holds the values for one income-tax year (6 April to 5 April) and the
matching corporation-tax financial year (1 April to 31 March). Each value carries its unit, the
statutory authority, the GOV.UK source URL, the date it was retrieved and whether it was verified.
Nothing in the engine hard-codes a rate or threshold: computations ask this store, and every value
they use is recorded so each output line can show its parameters.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..dates import fy_of, fy_label_to_params_label, tax_year_of
from ..models import ParamUse
from ..money import bp, to_pence

PARAMS_DIR = Path(__file__).parent


class MissingParam(LookupError):
    pass


@dataclass
class ParamFile:
    label: str
    path: Path
    doc: Dict[str, Any]

    @property
    def params(self) -> Dict[str, Dict[str, Any]]:
        return self.doc["params"]


@dataclass
class ParamStore:
    files: Dict[str, ParamFile] = field(default_factory=dict)
    used: Dict[Tuple[str, str], ParamUse] = field(default_factory=dict)

    @classmethod
    def load(cls, directory: Optional[Path] = None) -> "ParamStore":
        directory = Path(directory or PARAMS_DIR)
        store = cls()
        for p in sorted(directory.glob("*.json")):
            doc = json.loads(p.read_text(encoding="utf-8"))
            if doc.get("schema") != "brg_tax/params@1":
                continue
            store.files[doc["label"]] = ParamFile(doc["label"], p, doc)
        if not store.files:
            raise MissingParam(f"no parameter files found in {directory}")
        return store

    # ------------------------------------------------------------------ lookup
    @property
    def labels(self) -> List[str]:
        return sorted(self.files)

    def label_for(self, period: str, on: date) -> str:
        return tax_year_of(on) if period == "tax_year" else fy_label_to_params_label(fy_of(on))

    def period_of(self, key: str) -> str:
        for f in self.files.values():
            if key in f.params:
                return f.params[key]["period"]
        raise MissingParam(f"parameter {key!r} is not defined in any year")

    def entry(self, key: str, on: date) -> Tuple[str, Dict[str, Any]]:
        label = self.label_for(self.period_of(key), on)
        f = self.files.get(label)
        if f is None:
            raise MissingParam(f"no parameter file for {label} (needed for {key} on {on})")
        if key not in f.params:
            raise MissingParam(f"parameter {key!r} missing for {label}")
        return label, f.params[key]

    def get(self, key: str, on: date) -> ParamUse:
        """Look up a parameter for a date and record the use."""
        label, e = self.entry(key, on)
        value = e["value"]
        eff = e.get("effective_from")
        if eff and on < date.fromisoformat(eff):
            value = None
        use = ParamUse(key=key, year=label, value=value, verified=bool(e.get("verified")),
                       source_url=e.get("source_url", ""), authority=e.get("authority", ""))
        self.used[(key, label)] = use
        return use

    def value(self, key: str, on: date) -> Any:
        return self.get(key, on).value

    def rate(self, key: str, on: date) -> Tuple[int, ParamUse]:
        u = self.get(key, on)
        if u.value is None:
            return 0, u
        return bp(u.value), u

    def money(self, key: str, on: date) -> Tuple[Optional[int], ParamUse]:
        u = self.get(key, on)
        return (None if u.value is None else to_pence(u.value)), u

    def has(self, key: str, label: str) -> bool:
        f = self.files.get(label)
        return bool(f and key in f.params)

    # ------------------------------------------------------------------ status
    def verification(self, labels: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        rows = []
        for label in (labels or self.labels):
            f = self.files.get(label)
            if not f:
                continue
            for key, e in f.params.items():
                rows.append({
                    "year": label, "key": key, "value": e["value"], "unit": e.get("unit"), "period": e.get("period"),
                    "verified": bool(e.get("verified")), "retrieved": e.get("retrieved"), "source_url": e.get("source_url"),
                    "authority": e.get("authority"), "note": e.get("note"), "seed_confidence": e.get("seed_confidence"),
                    "effective_from": e.get("effective_from"), "verify_result": e.get("verify_result"),
                })
        return {"total": len(rows), "verified": sum(r["verified"] for r in rows), "rows": rows}
