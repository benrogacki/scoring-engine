"""The rules library: loading, lookup and validation.

Rules live in one YAML file per domain. Each rule carries its statutory authority and HMRC guidance,
a certainty level (rule / judgment / election), effective dates and the parameters it relies on.
``validate`` fails the build when a rule has no authority, when versions of the same id overlap in
time, when a referenced parameter is missing for a year in use, or when the engine cites a rule id
that does not exist.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

RULES_DIR = Path(__file__).parent
FAR_FUTURE = date(9999, 12, 31)


class Effective(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    from_: date = Field(alias="from")
    to: Optional[date] = None

    def contains(self, d: date) -> bool:
        return self.from_ <= d <= (self.to or FAR_FUTURE)

    def overlaps(self, start: date, end: date) -> bool:
        return self.from_ <= end and start <= (self.to or FAR_FUTURE)


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    domain: str = ""
    title: str
    question: str
    applies: Literal["transaction", "computation", "deadline"] = "transaction"
    conditions: Dict[str, Any] = Field(default_factory=dict)
    outcome: Dict[str, Any] = Field(default_factory=dict)
    certainty: Literal["rule", "judgment", "election"]
    authority: List[str]
    guidance: List[str] = Field(default_factory=list)
    entity_types: List[Literal["company", "sole_trader"]]
    effective: Effective
    params: List[str] = Field(default_factory=list)
    notes: str = ""
    priority: int = 0
    overlay: bool = False
    fact_needed: Optional[str] = None
    # judgment rules
    factors: List[str] = Field(default_factory=list)
    authorities: List[str] = Field(default_factory=list)
    default: Dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""
    # deadline rules
    anchor: Optional[str] = None
    offset: Dict[str, int] = Field(default_factory=dict)
    fixed: Dict[str, int] = Field(default_factory=dict)
    when: Optional[str] = None
    kind: Optional[str] = None

    @field_validator("authority")
    @classmethod
    def _authority(cls, v: List[str]) -> List[str]:
        if not v or not all(isinstance(a, str) and a.strip() for a in v):
            raise ValueError("every rule needs at least one statutory authority")
        return v

    @property
    def specificity(self) -> int:
        return len(self.conditions)

    def card(self) -> Dict[str, Any]:
        """Compact form for outputs and the dashboard."""
        d = {"id": self.id, "domain": self.domain, "title": self.title, "question": self.question,
             "certainty": self.certainty, "authority": self.authority, "guidance": self.guidance,
             "effective": {"from": self.effective.from_.isoformat(), "to": self.effective.to.isoformat() if self.effective.to else None},
             "params": self.params, "notes": self.notes, "applies": self.applies}
        if self.certainty == "judgment":
            d.update(factors=self.factors, authorities=self.authorities, default=self.default, reasoning=self.reasoning)
        return d


class RuleError(LookupError):
    pass


class RuleBook:
    def __init__(self, rules: List[Rule], files: Dict[str, Dict[str, Any]]):
        self.rules = rules
        self.files = files
        self._by_id: Dict[str, List[Rule]] = {}
        for r in rules:
            self._by_id.setdefault(r.id, []).append(r)

    @classmethod
    def load(cls, directory: Optional[Path] = None) -> "RuleBook":
        directory = Path(directory or RULES_DIR)
        rules, files = [], {}
        for p in sorted(directory.glob("*.yaml")):
            doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            domain = doc.get("domain") or p.stem
            files[p.name] = {"domain": domain, "citations_checked": bool(doc.get("citations_checked")), "count": len(doc.get("rules", []))}
            for i, raw in enumerate(doc.get("rules", [])):
                raw = dict(raw)
                raw.setdefault("domain", domain)
                try:
                    rules.append(Rule(**raw))
                except Exception as exc:  # pydantic ValidationError, with location
                    rid = raw.get("id", f"#{i}")
                    raise RuleError(f"{p.name}: rule {rid}: {exc}") from exc
        return cls(rules, files)

    def get(self, rule_id: str, on: Optional[date] = None) -> Rule:
        versions = self._by_id.get(rule_id)
        if not versions:
            raise RuleError(f"unknown rule {rule_id}")
        if on is None:
            return versions[-1]
        for r in versions:
            if r.effective.contains(on):
                return r
        return versions[-1]

    def exists(self, rule_id: str) -> bool:
        return rule_id in self._by_id

    def transaction_rules(self, on: date, entity_type: str) -> List[Rule]:
        return [r for r in self.rules if r.applies == "transaction" and r.effective.contains(on) and entity_type in r.entity_types]

    def by_applies(self, applies: str) -> List[Rule]:
        return [r for r in self.rules if r.applies == applies]

    def coverage(self) -> Dict[str, Any]:
        by_domain: Dict[str, Dict[str, int]] = {}
        for r in self.rules:
            d = by_domain.setdefault(r.domain, {"rule": 0, "judgment": 0, "election": 0})
            d[r.certainty] += 1
        return {"total": len(self.rules), "by_domain": by_domain,
                "citations_checked": all(f["citations_checked"] for f in self.files.values())}


# --------------------------------------------------------------------------- validation
def engine_rule_refs() -> Dict[str, List[str]]:
    """Rule ids the engine modules cite (each module declares USES_RULES)."""
    from importlib import import_module
    refs: Dict[str, List[str]] = {}
    for mod in ("router", "ct", "capital_allowances", "vat", "extraction", "sole_trader", "deadlines"):
        m = import_module(f"brg_tax.engine.{mod}")
        for rid in getattr(m, "USES_RULES", []):
            refs.setdefault(rid, []).append(mod)
    return refs


def _param_coverage(store) -> Dict[str, tuple]:
    out = {}
    for label, f in store.files.items():
        ty, fy = f.doc["tax_year"], f.doc["financial_year"]
        start = min(date.fromisoformat(ty["start"]), date.fromisoformat(fy["start"]))
        end = max(date.fromisoformat(ty["end"]), date.fromisoformat(fy["end"]))
        out[label] = (start, end)
    return out


def validate(book: RuleBook, store, years: Optional[Iterable[str]] = None, check_engine: bool = True) -> List[Dict[str, str]]:
    """Return a list of problems; an empty list means the library is valid."""
    problems: List[Dict[str, str]] = []

    def bad(rule_id: str, msg: str) -> None:
        problems.append({"rule": rule_id, "problem": msg})

    years = list(years or store.labels)
    coverage = _param_coverage(store)

    for rid, versions in book._by_id.items():
        for i, a in enumerate(versions):
            for b in versions[i + 1:]:
                if a.effective.overlaps(b.effective.from_, b.effective.to or FAR_FUTURE):
                    bad(rid, f"overlapping effective dates: {a.effective.from_}..{a.effective.to} and {b.effective.from_}..{b.effective.to}")
    for r in book.rules:
        if r.certainty == "judgment":
            if not r.factors:
                bad(r.id, "judgment rule has no factors")
            if not r.authorities:
                bad(r.id, "judgment rule has no leading authorities")
            if not r.default:
                bad(r.id, "judgment rule has no proposed default")
        if r.outcome.get("ct") == "review_fact" or r.outcome.get("vat") == "review_fact":
            if not r.fact_needed:
                bad(r.id, "review_fact outcome without fact_needed")
        if r.applies == "deadline" and not r.anchor:
            bad(r.id, "deadline rule has no anchor")
        for key in r.params:
            for y in years:
                if y not in coverage:
                    continue
                start, end = coverage[y]
                if not r.effective.overlaps(start, end):
                    continue
                if not store.has(key, y):
                    bad(r.id, f"parameter {key} missing for {y}")
        for v in r.conditions.values():
            for item in (v if isinstance(v, list) else [v]):
                if isinstance(item, dict):
                    for op, operand in item.items():
                        if isinstance(operand, str) and operand.startswith("param:"):
                            key = operand[6:]
                            if key not in r.params:
                                bad(r.id, f"condition compares with {key} but it is not listed in params")
    if check_engine:
        for rid, mods in engine_rule_refs().items():
            if not book.exists(rid):
                bad(rid, f"cited by engine module(s) {', '.join(mods)} but not defined")
    for y in years:
        if y not in store.files:
            bad("-", f"no parameter file for year in use {y}")
    return problems
