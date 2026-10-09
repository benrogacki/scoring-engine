"""What changed since the previous run: client changes and law changes."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Dict, List, Optional

SEV = {"critical": 3, "serious": 2, "warning": 1, "info": 0}


def _h(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:12]


def _flags(c: Dict[str, Any], rule_prefix: str, min_sev: int = 0) -> List[Dict[str, Any]]:
    return [f for f in c.get("flags", []) if f["rule"].startswith(rule_prefix) and SEV[f["severity"]] >= min_sev]


def diff_runs(prev: Optional[Dict[str, Any]], cur: Dict[str, Any], liability_threshold: int = 10000) -> Dict[str, Any]:
    out: Dict[str, Any] = {"previous_as_of": prev["as_of"] if prev else None, "as_of": cur["as_of"],
                           "previous_fingerprint": prev["fingerprint"] if prev else None, "fingerprint": cur["fingerprint"], "changes": []}
    if not prev:
        out["note"] = "No previous run supplied; nothing to compare."
        return out
    ch = out["changes"]

    def add(kind: str, severity: str, title: str, detail: str, client_id: Optional[str] = None, **extra: Any) -> None:
        ch.append({"kind": kind, "severity": severity, "client_id": client_id, "title": title, "detail": detail, **extra})

    pc = {c["id"]: c for c in prev["clients"]}
    for c in cur["clients"]:
        p = pc.get(c["id"])
        cid = c["id"]
        if p is None:
            add("client", "info", "New client", f"{c['name']} added", cid)
            continue
        d = c["liability"] - p["liability"]
        if abs(d) >= liability_threshold:
            add("client", "warning" if d > 0 else "info", "Estimated liability moved",
                f"{c['name']}: £{p['liability'] / 100:,.2f} -> £{c['liability'] / 100:,.2f}", cid, delta=d)
        if c["status"] != p["status"]:
            add("client", "warning" if c["status"] in ("blocked", "attention") else "info", "Status changed", f"{c['name']}: {p['status']} -> {c['status']}", cid)
        if c["health"]["status"] != p["health"]["status"]:
            add("client", "critical" if c["health"]["status"] == "fail" else "info", "Data health changed",
                f"{c['name']}: {p['health']['status']} -> {c['health']['status']}", cid)
        for prefix, title in (("VAT-REG", "VAT registration threshold"), ("EXT-DLA", "Director's loan account"), ("SA-MTD", "MTD for Income Tax")):
            now = {f["message"] for f in _flags(c, prefix, 1)}
            before = {f["message"] for f in _flags(p, prefix, 1)}
            for msg in sorted(now - before):
                sev = max((f["severity"] for f in _flags(c, prefix, 1) if f["message"] == msg), key=lambda s: SEV[s])
                add("client", sev, title, msg, cid)
        pa = (p.get("profile") or {}).get("associated_companies")
        ca = (c.get("profile") or {}).get("associated_companies")
        if pa != ca:
            add("client", "serious", "Associated companies changed", f"{c['name']}: {pa} -> {ca}; CT limits change", cid)
        prev_ids = {r["id"] for r in p.get("review", [])}
        new_items = [r for r in c.get("review", []) if r["id"] not in prev_ids]
        if new_items:
            add("client", "warning", "New review items", f"{c['name']}: " + "; ".join(r["title"] for r in new_items), cid,
                review_ids=[r["id"] for r in new_items])
        decided = [r for r in c.get("review", []) if r["status"] == "decided" and any(x["id"] == r["id"] and x["status"] == "open" for x in p.get("review", []))]
        if decided:
            add("client", "info", "Review items decided", f"{c['name']}: {len(decided)} item(s)", cid)
    for cid in set(pc) - {c["id"] for c in cur["clients"]}:
        add("client", "info", "Client removed", pc[cid]["name"], cid)

    # law changes: rules and parameters that are new or changed, or have become effective
    prev_rules = {r["id"]: _h(r) for r in prev["rules"]["cards"]}
    prev_as_of, cur_as_of = date.fromisoformat(prev["as_of"]), date.fromisoformat(cur["as_of"])
    for r in cur["rules"]["cards"]:
        affected = _affected(cur, r["effective"]["from"], r.get("applies"))
        if r["id"] not in prev_rules:
            add("law", "warning", "New rule", f"{r['id']} {r['title']}", affected=affected, rule=r["id"])
        elif prev_rules[r["id"]] != _h(r):
            add("law", "warning", "Rule changed", f"{r['id']} {r['title']}", affected=affected, rule=r["id"])
        eff = date.fromisoformat(r["effective"]["from"])
        if prev_as_of < eff <= cur_as_of and affected:
            add("law", "serious", "Rule now in force", f"{r['id']} {r['title']} (from {eff.isoformat()})", affected=affected, rule=r["id"])
    prev_params = {(x["year"], x["key"]): x for x in prev["params"]["rows"]}
    for x in cur["params"]["rows"]:
        k = (x["year"], x["key"])
        old = prev_params.get(k)
        users = [c["id"] for c in cur["clients"] if [x["key"], x["year"]] in [list(u) for u in c.get("params_used", [])]]
        if old is None:
            add("law", "info", "New parameter", f"{x['key']} {x['year']} = {x['value']}", affected=users)
        elif old["value"] != x["value"]:
            add("law", "serious", "Parameter value changed", f"{x['key']} {x['year']}: {old['value']} -> {x['value']}", affected=users)
        elif old["verified"] != x["verified"]:
            add("law", "info", "Parameter verification changed", f"{x['key']} {x['year']}: verified {old['verified']} -> {x['verified']}", affected=users)
        eff = x.get("effective_from")
        if eff and prev_as_of < date.fromisoformat(eff) <= cur_as_of and users:
            add("law", "serious", "Parameter now in force", f"{x['key']} {x['year']} from {eff}", affected=users)
    ch.sort(key=lambda c: (-SEV[c["severity"]], c["kind"], c.get("client_id") or ""))
    return out


def _affected(run: Dict[str, Any], eff_from: str, applies: Optional[str]) -> List[str]:
    eff = date.fromisoformat(eff_from)
    return [c["id"] for c in run["clients"] if date.fromisoformat(c["period"]["start"]) <= eff <= date.fromisoformat(run["as_of"])]
