"""Run the whole engine over a set of clients and assemble a JSON-ready result."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..ingest import load_clients
from ..models import ClientData
from ..params import ParamStore
from ..rules import RuleBook, validate
from . import capital_allowances, ct as ct_mod, deadlines, extraction, health, router, sole_trader, vat
from .context import Ctx

SCHEMA = "brg_tax/run@1"


def _dump(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [_dump(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _dump(v) for k, v in obj.items()}
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


def run_client(data: ClientData, store: ParamStore, book: RuleBook, policy: Dict[str, Any],
               decisions: Dict[str, Dict[str, Any]], as_of: date) -> Dict[str, Any]:
    c = data.client
    ctx = Ctx(params=store, rules=book, policy=policy, decisions=decisions, as_of=as_of, client=c)
    per = c.period
    hc = health.run_checks(data, store, as_of)
    treatments = router.route(ctx, data.transactions, per.start, per.end)
    strategy = (policy.get("capital_allowances", {}).get("strategy_overrides", {}) or {}).get(c.id) or policy.get("capital_allowances", {}).get("default_strategy", "max")
    ca = capital_allowances.compute(ctx, data.assets, per.start, per.end, strategy)
    ca_alt = capital_allowances.all_strategies(ctx, data.assets, per.start, per.end)
    out: Dict[str, Any] = {
        "id": c.id, "name": c.name, "entity_type": c.entity_type, "package": c.package, "region": c.region, "synthetic": c.synthetic,
        "period": {"start": per.start.isoformat(), "end": per.end.isoformat(), "days": per.days}, "notes": c.notes,
        "health": hc, "trusted": hc["status"] != "fail",
        "treatments": _dump(treatments),
        "ca": {"strategy": ca.strategy, "lines": _dump(ca.lines), "allowances": ca.allowances, "charges": ca.charges, "aia_limit": ca.aia_limit,
               "aia_used": ca.aia_used, "pools_cf": ca.pools_cf, "single_pools": ca.single_pools, "sba": ca.sba, "schedule": ca.schedule,
               "strategies": ca_alt},
        "profile": _dump(c),
    }
    extra: Dict[str, Any] = {}
    if c.entity_type == "company":
        res = ct_mod.compute(ctx, data, treatments, ca)
        dla = extraction.dla_monitor(ctx, data)
        ir = extraction.ir35(ctx, data, res)
        opt = extraction.optimise(ctx, data, res, dla)
        # CA strategy sensitivity for the optimiser: change in profit before directors' costs
        opt["model"]["ca_options"] = {k: ca.net - v for k, v in ca_alt.items()}
        out["computation"] = {"kind": "ct", "lines": _dump(res.lines), "accounting_profit": res.accounting_profit, "trading_profit": res.trading_profit,
                              "ttp": res.ttp, "liability": res.ct, "slices": res.slices, "schedule": res.schedule,
                              "payment_due": res.payment_due.isoformat() if res.payment_due else None, "losses_cf": res.losses_cf,
                              "provisional": res.provisional}
        out["dla"] = dla
        out["ir35"] = ir
        out["extraction"] = opt
        extra["s455"] = dla.get("total_s455", 0)
        out["liability"] = res.ct
        out["s455"] = dla.get("total_s455", 0)
    else:
        sa = sole_trader.compute(ctx, data, treatments, ca)
        out["computation"] = {"kind": "sa", "tax_year": sa.tax_year, "lines": _dump(sa.lines), "accounting_profit": sa.accounting_profit,
                              "taxable_profit": sa.taxable_profit, "income_tax": sa.income_tax, "class4": sa.class4, "class2": sa.class2,
                              "class2_status": sa.class2_status, "liability": sa.total, "poa_next": sa.poa_next, "balancing": sa.balancing,
                              "provisional": sa.provisional}
        out["sa"] = {"mtd": sa.mtd, "comparator": sa.comparator, "comparator_model": sa.comparator_model}
        extra["mtd_from"] = sa.mtd.get("mandated_from")
        out["liability"] = sa.total
        out["s455"] = 0
    out["vat"] = vat.monitor(ctx, data, treatments)
    out["deadlines"] = deadlines.generate(ctx, extra)
    out["review"] = _dump(ctx.review)
    out["flags"] = ctx.flags
    out["params_used"] = sorted({(u.key, u.year) for u in store.used.values()})
    open_items = [r for r in ctx.review if r.status == "open"]
    worst_flag = max([{"info": 0, "warning": 1, "serious": 2, "critical": 3}[f["severity"]] for f in ctx.flags] or [0])
    if not out["trusted"]:
        status = "blocked"
    elif open_items or out["computation"]["provisional"]:
        status = "review"
    elif worst_flag >= 2:
        status = "attention"
    else:
        status = "ready"
    out["status"] = status
    out["open_review"] = len(open_items)
    return out


def load_decisions(path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    if not path or not Path(path).exists():
        return {}
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return doc.get("decisions", doc) if isinstance(doc, dict) else {}


def fingerprint(paths: List[Path], extra: Dict[str, Any]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(str(p.name).encode())
        h.update(p.read_bytes())
    h.update(json.dumps(extra, sort_keys=True, default=str).encode())
    return h.hexdigest()[:16]


def run_all(clients_dir: Path, policy: Dict[str, Any], decisions: Dict[str, Dict[str, Any]], as_of: date,
            store: Optional[ParamStore] = None, book: Optional[RuleBook] = None) -> Dict[str, Any]:
    store = store or ParamStore.load()
    book = book or RuleBook.load()
    problems = validate(book, store)
    datas = load_clients(Path(clients_dir))
    results = []
    for d in datas:
        store.used.clear()
        results.append(run_client(d, store, book, policy, decisions, as_of))
    files = [p for p in Path(clients_dir).rglob("*") if p.is_file()]
    files += [f.path for f in store.files.values()] + sorted((Path(__file__).parent.parent / "rules").glob("*.yaml"))
    review = [r for c in results for r in c["review"]]
    dl = sorted([e for c in results for e in c["deadlines"]], key=lambda e: e["date"])
    return {
        "schema": SCHEMA, "as_of": as_of.isoformat(), "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fingerprint": fingerprint(files, {"policy": policy, "decisions": decisions, "as_of": as_of.isoformat()}),
        "policy": policy, "clients": results, "review_queue": review, "deadlines": dl,
        "rules": {"cards": [r.card() for r in book.rules], "coverage": book.coverage(), "problems": problems,
                  "files": book.files},
        "params": store.verification(),
        "decisions_loaded": len(decisions),
        "totals": {
            "clients": len(results),
            "liability": sum(c["liability"] for c in results),
            "s455": sum(c["s455"] for c in results),
            "open_review": sum(c["open_review"] for c in results),
            "health_fail": sum(1 for c in results if c["health"]["status"] == "fail"),
        },
    }
