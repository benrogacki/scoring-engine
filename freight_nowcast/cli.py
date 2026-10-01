"""Command line: ``freight-nowcast live | fetch | run | probe | demo | inspect | ais-listen``."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

from . import engine
from .catalog import CatalogError, load_catalog
from .dashboard import write_dashboard
from .demo import write_demo_cache
from .report import write_outputs
from .live import fetch_all, probe, required_failures
from .sources import SourceError


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="freight-nowcast",
                                description="Real-economy momentum from published freight series.")
    p.add_argument("--catalog", type=Path, help="Series catalog JSON (default: config/freight_nowcast.json)")
    sub = p.add_subparsers(dest="command", required=True)

    f = sub.add_parser("fetch", help="Download every enabled series from its publisher into the live cache")
    f.add_argument("--cache", type=Path, help="Cache directory (default: catalog cache_dir)")
    f.add_argument("--only", nargs="*", help="Fetch only these series ids")

    lv = sub.add_parser("live", help="fetch + run on real data in one step (what the scheduled job runs)")
    lv.add_argument("--cache", type=Path)
    lv.add_argument("--as-of", type=_date, default=date.today())
    lv.add_argument("--out", type=Path, default=Path("out/freight/live"))
    lv.add_argument("--strict", action="store_true", help="Exit 1 if a required series failed to fetch")

    pr = sub.add_parser("probe", help="Try every source, print what came back and GENESIS table codes")
    pr.add_argument("--only", nargs="*")

    r = sub.add_parser("run", help="Build z-scores, composites, turning points, validation and the capstone feed")
    r.add_argument("--cache", type=Path)
    r.add_argument("--as-of", type=_date, default=date.today())
    r.add_argument("--out", type=Path, default=Path("out/freight"))

    d = sub.add_parser("demo", help="Write synthetic series to a cache and run on them (offline trial)")
    d.add_argument("--cache", type=Path, default=Path("out/freight-demo-cache"))
    d.add_argument("--out", type=Path, default=Path("examples/freight/output"))
    d.add_argument("--as-of", type=_date, default=date.today())
    d.add_argument("--seed", type=int, default=11)

    i = sub.add_parser("inspect", help="List variables and attribute codes of a GENESIS table to set catalog filters")
    g = i.add_mutually_exclusive_group(required=True)
    g.add_argument("--genesis", metavar="TABLE", help="Table code, e.g. 42191-0001 (needs credentials)")
    g.add_argument("--file", type=Path, help="A saved GENESIS ffcsv download")

    a = sub.add_parser("ais-listen", help="Sample aisstream.io for the catalog's ports and append counts")
    a.add_argument("--minutes", type=float, default=10.0)
    a.add_argument("--out", type=Path, default=Path("data/freight/ais_port_counts.csv"))
    return p


def _print_result(paths, result) -> None:
    for w in result.warnings:
        print(f"  ! {w}")
    c = result.composite
    if c.composite:
        m = max(c.composite)
        print(f"Composite {m[0]}-{m[1]:02d}: {c.composite[m]:+.2f} z  phase {result.phases.get(m, 'n/a')}"
              f"{'  (provisional)' if c.provisional.get(m) else ''}")
        for code, g in result.geographies.items():
            gm = max(g.composite)
            print(f"  {code:6s} {gm[0]}-{gm[1]:02d}: {g.composite[gm]:+.2f} z  {result.geo_phases[code].get(gm, '')}")
    for v in result.validation:
        print(f"  evidence {v.indicator} -> {v.target}: {v.verdict}")
    for name, path in paths.items():
        print(f"  -> {path}")


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_catalog(args.catalog)
    except (CatalogError, OSError, json.JSONDecodeError) as exc:
        print(f"error: catalog: {exc}", file=sys.stderr)
        return 2
    base = Path(cfg["_base_dir"])
    cache = getattr(args, "cache", None) or base / cfg.get("cache_dir", "data/freight/live")
    failed: list = []

    if args.command == "probe":
        return 1 if probe(cfg, args.only) else 0

    if args.command in ("fetch", "live"):
        try:
            manifest = fetch_all(cfg, cache, getattr(args, "only", None))
        except SourceError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        failed = required_failures(cfg, manifest)
        if failed:
            print(f"  required series not fetched: {', '.join(failed)}")
        if args.command == "fetch":
            return 1 if failed else 0

    if args.command == "inspect":
        from .sources import genesis
        try:
            text = args.file.read_text(encoding="utf-8-sig") if args.file else \
                genesis.GenesisClient.from_env().tablefile(args.genesis)
        except (SourceError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(genesis.inspect_ffcsv(text), indent=2, ensure_ascii=False))
        return 0

    if args.command == "ais-listen":
        from .sources import ais
        try:
            rows = ais.listen(ais.ports_from_config(cfg), args.minutes, args.out)
        except SourceError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        for r in rows:
            print(f"  {r['port']:12s} vessels {r['vessels']:4d}  stationary {r['stationary']:4d}")
        print(f"  -> {args.out}")
        return 0

    if args.command == "demo":
        try:
            write_demo_cache(args.cache, args.as_of, args.seed)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"Wrote synthetic demo series to {args.cache}/ (not real data)")

    try:
        result = engine.run(cfg, cache, args.as_of)
    except SourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    paths = write_outputs(result, cfg, args.out)
    paths["dashboard"] = write_dashboard(result, cfg, args.out / "dashboard.html")
    _print_result(paths, result)
    if args.command == "live" and args.strict and failed:
        return 1
    return 0
