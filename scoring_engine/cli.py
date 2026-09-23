"""Command-line entry point: ``credit-score run`` and ``credit-score sample``."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

from . import engine
from .config import load_config
from .loader import LedgerError, merge_customers, parse_date, read_customers, read_ledger
from .report import write_outputs
from .sample_data import generate


def _date_arg(value: str) -> date:
    try:
        parsed = parse_date(value)
    except LedgerError as exc:
        raise argparse.ArgumentTypeError(str(exc))
    if parsed is None:
        raise argparse.ArgumentTypeError("date is required")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="credit-score",
        description="Score a debtor ledger for credit risk, recommend credit limits and prioritise collections.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Score a debtor ledger")
    run.add_argument("--ledger", type=Path, required=True, help="Invoice-level debtor ledger CSV")
    run.add_argument("--customers", type=Path, help="Customer master CSV (credit limits, terms)")
    run.add_argument("--as-of", type=_date_arg, default=date.today(), help="Scoring date (default: today)")
    run.add_argument("--config", type=Path, help="JSON config overriding default weights/policies")
    run.add_argument("--out", type=Path, default=Path("out"), help="Output directory (default: ./out)")

    sample = sub.add_parser("sample", help="Generate a synthetic ledger to try the engine")
    sample.add_argument("--out", type=Path, default=Path("examples"), help="Directory for sample CSVs")
    sample.add_argument("--as-of", type=_date_arg, default=date.today())
    sample.add_argument("--seed", type=int, default=7)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "sample":
        n_cust, n_inv = generate(args.out / "ledger.csv", args.out / "customers.csv", args.as_of, args.seed)
        print(f"Wrote {n_inv} invoices for {n_cust} customers to {args.out}/")
        return 0

    try:
        config = load_config(args.config)
        invoices = read_ledger(args.ledger)
        customers = merge_customers(invoices, read_customers(args.customers))
    except (LedgerError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result = engine.run(invoices, customers, args.as_of, config)
    paths = write_outputs(result, config, args.out)
    sm = result.summary
    print(f"Scored {sm['customers']} customers as at {args.as_of.isoformat()}")
    print(f"  Receivables {sm['total_outstanding']:,.0f}  overdue {sm['total_overdue']:,.0f} ({sm['overdue_pct']:.1%})")
    print("  Grades: " + "  ".join(f"{g}={d['customers']}" for g, d in sm["by_grade"].items()))
    print(f"  Collections worklist: {len(result.worklist)} customers  {sm['collection_tiers']}")
    for name, path in paths.items():
        print(f"  -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
