"""``brg-tax`` command line: params-update | check | run | diff | sample | merge-decisions."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

from .dashboard import render
from .engine.diff import diff_runs
from .engine.run import load_decisions, run_all
from .money import fmt
from .params import ParamStore
from .report import write_outputs
from .rules import RuleBook, validate


def _date(v: str) -> date:
    try:
        return date.fromisoformat(v)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"dates are YYYY-MM-DD: {v}") from exc


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="brg-tax", description="BRG Tax Engine: cited UK tax rules, computations, optimiser and audit trail.")
    sub = p.add_subparsers(dest="cmd", required=True)

    u = sub.add_parser("params-update", help="Fetch each parameter's GOV.UK source and mark it verified if the value is confirmed")
    u.add_argument("--year", action="append", help="Tax year label, e.g. 2026-27 (repeatable; default all)")
    u.add_argument("--dry-run", action="store_true", help="Check but do not write the parameter files")

    c = sub.add_parser("check", help="Validate the rules library and parameter files")
    c.add_argument("--strict", action="store_true", help="Also fail if any parameter is unverified")

    r = sub.add_parser("run", help="Run every client and write the outputs")
    r.add_argument("--clients", type=Path, default=Path("clients"))
    r.add_argument("--policy", type=Path, default=Path("policy.json"))
    r.add_argument("--decisions", type=Path, help="Reviewer decisions JSON (exported from the dashboard)")
    r.add_argument("--out", type=Path, default=Path("out"))
    r.add_argument("--as-of", type=_date, default=date.today())
    r.add_argument("--previous", type=Path, help="Output folder of a previous run, for 'changes since last run'")
    r.add_argument("--strict", action="store_true", help="Exit non-zero if any client's data health fails")

    d = sub.add_parser("diff", help="Compare two run output folders")
    d.add_argument("previous", type=Path)
    d.add_argument("current", type=Path)
    d.add_argument("--json", action="store_true", help="Print JSON instead of text")

    s = sub.add_parser("sample", help="Write the synthetic sample clients")
    s.add_argument("--out", type=Path, default=Path("clients"))

    m = sub.add_parser("merge-decisions", help="Merge dashboard decision exports into one decisions file")
    m.add_argument("files", type=Path, nargs="+")
    m.add_argument("--into", type=Path, required=True)
    return p


def _load_run(folder: Path) -> dict:
    f = Path(folder) / "run.json"
    if not f.exists():
        raise SystemExit(f"{folder}: run.json not found (is this a brg-tax run output folder?)")
    return json.loads(f.read_text(encoding="utf-8"))


def cmd_check(args) -> int:
    store, book = ParamStore.load(), RuleBook.load()
    problems = validate(book, store)
    cov = book.coverage()
    pv = store.verification()
    print(f"Rules: {cov['total']} across {len(cov['by_domain'])} domains")
    for dom, n in sorted(cov["by_domain"].items()):
        print(f"  {dom:<26} {n['rule']:>3} rule  {n['judgment']:>3} judgment  {n['election']:>3} election")
    print(f"Parameters: {pv['verified']} of {pv['total']} verified across {', '.join(store.labels)}")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems:
            print(f"  {p['rule']}: {p['problem']}")
        return 1
    print("Rules library valid: every rule has an authority, no overlapping dates, parameters present for every year in use.")
    if pv["verified"] < pv["total"]:
        print(f"WARNING: {pv['total'] - pv['verified']} parameter values are unverified - run `brg-tax params-update` with network access.")
        if args.strict:
            return 1
    return 0


def cmd_run(args) -> int:
    policy = json.loads(args.policy.read_text(encoding="utf-8")) if args.policy.exists() else {}
    decisions = load_decisions(args.decisions)
    run = run_all(args.clients, policy, decisions, args.as_of)
    prev = _load_run(args.previous) if args.previous else None
    threshold = int(float((policy.get("risk_appetite") or {}).get("liability_change_alert", 100)) * 100)
    run["changes"] = diff_runs(prev, run, threshold)
    written = write_outputs(run, args.out, render(run))
    t = run["totals"]
    print(f"BRG Tax Engine run as of {run['as_of']} · fingerprint {run['fingerprint']}")
    for c in run["clients"]:
        print(f"  {c['name']:<36} {c['status']:<10} {fmt(c['liability']):>14}  review {c['open_review']}  health {c['health']['status']}")
    print(f"Estimated liabilities {fmt(t['liability'])} · s455 exposure {fmt(t['s455'])} · open review items {t['open_review']}")
    pv = run["params"]
    if pv["verified"] < pv["total"]:
        print(f"WARNING: {pv['total'] - pv['verified']} of {pv['total']} parameter values unverified.")
    if run["rules"]["problems"]:
        print(f"WARNING: rules library has {len(run['rules']['problems'])} problem(s) - run `brg-tax check`.")
    print(f"Wrote {len(written)} files to {args.out}/ (open dashboard.html)")
    if args.strict and (t["health_fail"] or run["rules"]["problems"]):
        return 2
    return 0


def cmd_diff(args) -> int:
    out = diff_runs(_load_run(args.previous), _load_run(args.current))
    if args.json:
        print(json.dumps(out, indent=2))
        return 0
    print(f"Changes from {out['previous_as_of']} to {out['as_of']}: {len(out['changes'])}")
    for c in out["changes"]:
        print(f"  [{c['severity']:<8}] {c['kind']:<6} {c['title']}: {c['detail']}")
    return 0


def cmd_params_update(args) -> int:
    from .params_update import update
    summary = update(args.year, dry_run=args.dry_run)
    for label, s in summary.items():
        print(f"{label}: {s['verified']} verified, {s['unverified']} not confirmed, {s['fetch_failed']} fetch failed, {s['no_check']} without a check")
    print("Values are never changed automatically; edit any unconfirmed value by hand after checking the source." + (" (dry run - nothing written)" if args.dry_run else ""))
    return 0


def cmd_merge(args) -> int:
    merged = {}
    if args.into.exists():
        merged.update(load_decisions(args.into))
    for f in args.files:
        merged.update(load_decisions(f))
    args.into.write_text(json.dumps({"schema": "brg_tax/decisions@1", "decisions": merged}, indent=2) + "\n", encoding="utf-8")
    print(f"{len(merged)} decisions in {args.into}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "diff":
        return cmd_diff(args)
    if args.cmd == "params-update":
        return cmd_params_update(args)
    if args.cmd == "merge-decisions":
        return cmd_merge(args)
    if args.cmd == "sample":
        from .samples import generate
        for f in generate(args.out):
            print(f"wrote {f}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
