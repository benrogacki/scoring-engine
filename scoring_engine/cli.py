"""Command-line entry point: ``credit-score run | extract | sample``."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

from . import engine
from .config import load_config
from .dashboard import write_dashboard
from .loader import LedgerError, merge_customers, parse_date, read_customers, read_ledger, rows_to_customers, rows_to_invoices
from .report import scorecard_rows, worklist_rows, write_outputs
from .sample_data import generate
from .sources import write_rows_csv
from .sources import databricks as dbx
from .sources import netsuite as ns

SOURCE_ERRORS = (LedgerError, ValueError, OSError, ns.NetSuiteError, dbx.DatabricksError)


def _date_arg(value: str) -> date:
    try:
        parsed = parse_date(value)
    except LedgerError as exc:
        raise argparse.ArgumentTypeError(str(exc))
    if parsed is None:
        raise argparse.ArgumentTypeError("date is required")
    return parsed


def _add_source_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("data source")
    g.add_argument("--source", choices=["csv", "netsuite", "databricks"], default="csv",
                   help="Where to read the ledger from (default: csv)")
    g.add_argument("--ledger", type=Path, help="[csv] Invoice-level debtor ledger CSV")
    g.add_argument("--customers", type=Path, help="[csv] Customer master CSV (credit limits, terms)")
    g.add_argument("--invoices-table", help="[databricks] Table/view of invoices, e.g. finance.credit.ar_invoices")
    g.add_argument("--customers-table", help="[databricks] Table/view of customers")
    g.add_argument("--invoices-query", help="[netsuite/databricks] SQL file overriding the default invoices query")
    g.add_argument("--customers-query", help="[netsuite/databricks] SQL file overriding the default customers query")
    g.add_argument("--lookback-months", type=int, default=15,
                   help="[netsuite/databricks] Months of invoices to pull (default: 15)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="credit-score",
        description="Score a debtor ledger for credit risk, recommend credit limits and prioritise collections.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Score a debtor ledger")
    _add_source_args(run)
    run.add_argument("--as-of", type=_date_arg, default=date.today(), help="Scoring date (default: today)")
    run.add_argument("--config", type=Path, help="JSON config overriding default weights/policies")
    run.add_argument("--out", type=Path, default=Path("out"), help="Output directory (default: ./out)")
    run.add_argument("--currency", default="", help="Currency symbol for the dashboard, e.g. '£'")
    run.add_argument("--label", help="Data source label shown on the dashboard")
    run.add_argument("--write-table-prefix",
                     help="Also write results to Databricks tables <prefix>_scorecard and <prefix>_worklist")

    extract = sub.add_parser("extract", help="Pull the ledger from NetSuite/Databricks to CSV without scoring")
    _add_source_args(extract)
    extract.add_argument("--out", type=Path, default=Path("data"), help="Directory for ledger.csv / customers.csv")

    sample = sub.add_parser("sample", help="Generate a synthetic ledger to try the engine")
    sample.add_argument("--out", type=Path, default=Path("examples"), help="Directory for sample CSVs")
    sample.add_argument("--as-of", type=_date_arg, default=date.today())
    sample.add_argument("--seed", type=int, default=7)
    return parser


def fetch_rows(args) -> Tuple[list, list, str]:
    """Return raw (invoice rows, customer rows, label) for the chosen source."""
    if args.source == "netsuite":
        client = ns.NetSuiteClient.from_env()
        data = ns.fetch(client, args.lookback_months, args.invoices_query, args.customers_query)
        return data["invoices"], data["customers"], f"NetSuite {client.account_id}"
    if args.source == "databricks":
        conn = dbx.connect()
        try:
            data = dbx.fetch(conn, args.invoices_table, args.customers_table, args.lookback_months,
                             args.invoices_query, args.customers_query)
        finally:
            conn.close()
        return data["invoices"], data["customers"], f"Databricks {args.invoices_table or args.invoices_query}"
    raise ValueError("fetch_rows is only for netsuite/databricks sources")


def load_ledger(args):
    if args.source == "csv":
        if not args.ledger:
            raise ValueError("--ledger is required with --source csv")
        invoices = read_ledger(args.ledger)
        return invoices, merge_customers(invoices, read_customers(args.customers)), args.ledger.name
    inv_rows, cust_rows, label = fetch_rows(args)
    invoices = rows_to_invoices(inv_rows, f"{args.source} invoices")
    customers = rows_to_customers(cust_rows, f"{args.source} customers")
    return invoices, merge_customers(invoices, customers), label


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "sample":
        n_cust, n_inv = generate(args.out / "ledger.csv", args.out / "customers.csv", args.as_of, args.seed)
        print(f"Wrote {n_inv} invoices for {n_cust} customers to {args.out}/")
        return 0

    if args.command == "extract":
        if args.source == "csv":
            print("error: extract needs --source netsuite or --source databricks", file=sys.stderr)
            return 2
        try:
            inv_rows, cust_rows, label = fetch_rows(args)
            rows_to_invoices(inv_rows, f"{args.source} invoices")  # validate before writing
        except SOURCE_ERRORS as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        write_rows_csv(args.out / "ledger.csv", inv_rows)
        write_rows_csv(args.out / "customers.csv", cust_rows)
        print(f"Extracted {len(inv_rows)} invoices and {len(cust_rows)} customers from {label} to {args.out}/")
        return 0

    try:
        config = load_config(args.config)
        invoices, customers, label = load_ledger(args)
    except SOURCE_ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result = engine.run(invoices, customers, args.as_of, config)
    paths = write_outputs(result, config, args.out)
    paths["dashboard"] = write_dashboard(
        result, config, args.out / "dashboard.html", source=args.label or label, currency=args.currency
    )
    sm = result.summary
    print(f"Scored {sm['customers']} customers from {label} as at {args.as_of.isoformat()}")
    print(f"  Receivables {sm['total_outstanding']:,.0f}  overdue {sm['total_overdue']:,.0f} ({sm['overdue_pct']:.1%})")
    print("  Grades: " + "  ".join(f"{g}={d['customers']}" for g, d in sm["by_grade"].items()))
    print(f"  Collections worklist: {len(result.worklist)} customers  {sm['collection_tiers']}")
    for name, path in paths.items():
        print(f"  -> {path}")

    if args.write_table_prefix:
        try:
            conn = dbx.connect()
            try:
                for suffix, rows in (("scorecard", scorecard_rows(result, config)), ("worklist", worklist_rows(result))):
                    table = f"{args.write_table_prefix}_{suffix}"
                    n = dbx.write_table(conn, table, rows, args.as_of)
                    print(f"  -> {table} ({n} rows)")
            finally:
                conn.close()
        except SOURCE_ERRORS as exc:
            print(f"error writing to Databricks: {exc}", file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
