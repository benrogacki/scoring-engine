# Databricks notebook source
# MAGIC %md
# MAGIC # Credit-risk scoring job
# MAGIC Reads the debtor ledger from Unity Catalog, scores every customer, and writes:
# MAGIC * `<output_prefix>_scorecard` and `<output_prefix>_worklist` Delta tables, one set of rows per `as_of`, so history accumulates
# MAGIC * `<output_prefix>_runs`: one row per run (data health, backtest verdict, what changed, fingerprint)
# MAGIC * reports, `credit_feed.json` and `dashboard.html` to a Volume: one folder per `as_of`, plus `latest/`
# MAGIC
# MAGIC Every run checks the extract first (freshness, duplicates, reconciliation). If the checks **fail**, reports are
# MAGIC written for diagnosis but the tables are left untouched and the run fails, so nothing downstream acts on bad data.
# MAGIC
# MAGIC Runs from this repo (a job with a Git source, or a Git folder). The engine is pure Python, so nothing needs installing.
# MAGIC The job definition is in `databricks/credit_scoring_job.json`; setup notes are in `docs/integrations.md`.
# MAGIC
# MAGIC **`as_of`**: leave blank to score as at the last day of the previous month (the normal month-end run),
# MAGIC enter `today` for a mid-month view, or give a date (`YYYY-MM-DD`) to re-run a past month.

# COMMAND ----------

dbutils.widgets.text("invoices_table", "main.finance.credit_ar_invoices", "Invoices table/view")
dbutils.widgets.text("customers_table", "main.finance.credit_customers", "Customers table/view (optional)")
dbutils.widgets.text("output_prefix", "main.finance.credit_risk", "Output table prefix")
dbutils.widgets.text("output_volume", "/Volumes/main/finance/reports/credit_scoring", "Folder for reports")
dbutils.widgets.text("as_of", "", "Scoring date: blank = last month-end, 'today', or YYYY-MM-DD")
dbutils.widgets.text("policy_json", "", "Policy overrides as JSON (optional)")
dbutils.widgets.text("lookback_months", "15", "Months of invoices to read")
dbutils.widgets.text("currency", "", "Currency symbol for the dashboard")
dbutils.widgets.text("control_total", "", "AR ageing control total to reconcile to (optional)")

# COMMAND ----------

import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    """Walk up from the notebook's folder to the directory holding scoring_engine/."""
    for candidate in [start, *start.parents]:
        if (candidate / "scoring_engine" / "__init__.py").exists():
            return candidate
    raise RuntimeError(f"Could not find the scoring_engine package above {start}; run this notebook from the repo")


repo_root = str(_find_repo_root(Path(os.getcwd()).resolve()))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from scoring_engine.config import load_config
from scoring_engine.health import now_utc, source_info
from scoring_engine.loader import parse_date, rows_to_customers, rows_to_invoices
from scoring_engine.pipeline import job_summary, run_log_row, score_run, write_run
from scoring_engine.report import scorecard_rows, worklist_rows
from scoring_engine.sources import databricks as dbx

w = {k: dbutils.widgets.get(k).strip() for k in
     ["invoices_table", "customers_table", "output_prefix", "output_volume", "as_of", "policy_json",
      "lookback_months", "currency", "control_total"]}

if not w["as_of"]:
    as_of = date.today().replace(day=1) - timedelta(days=1)  # last day of previous month
elif w["as_of"].lower() == "today":
    as_of = date.today()
else:
    as_of = parse_date(w["as_of"])
config = load_config(overrides=json.loads(w["policy_json"]) if w["policy_json"] else None)
control_total = float(w["control_total"].replace(",", "")) if w["control_total"] else None
print(f"Scoring as at {as_of} from {w['invoices_table']} (engine at {repo_root})")

# COMMAND ----------

extracted_at = now_utc()
data = dbx.fetch(
    conn=None,
    spark=spark,
    invoices_table=w["invoices_table"],
    customers_table=w["customers_table"] or None,
    lookback_months=int(w["lookback_months"] or 15),
)
invoices = rows_to_invoices(data["invoices"], w["invoices_table"])
if not invoices:
    # Fail the run loudly rather than overwrite this month's results with an empty ledger.
    raise RuntimeError(f"No invoices returned from {w['invoices_table']}; check the view and the lookback window")
master = rows_to_customers(data["customers"], w["customers_table"] or "customers")
source = source_info("databricks", w["invoices_table"], invoices, master, extracted_at)
print(f"Loaded {len(invoices):,} invoices and {len(master):,} customers")

# Compare with the latest earlier run already in the scorecard table.
prev_as_of, prev_card = dbx.spark_previous_scorecard(spark, f"{w['output_prefix']}_scorecard", as_of)
run = score_run(invoices, master, as_of, config, source, previous=prev_card, previous_as_of=prev_as_of,
                control_total=control_total)
print(job_summary(run, source))

# COMMAND ----------

# Reports go to a Volume: one folder per as_of date, and latest/ for a stable path.
out_dir = Path(w["output_volume"]) / as_of.isoformat()
latest_dir = Path(w["output_volume"]) / "latest"
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    write_run(run, config, tmp, source, currency=w["currency"])
    for target in (out_dir, latest_dir):
        target.mkdir(parents=True, exist_ok=True)
        for f in tmp.iterdir():
            (target / f.name).write_bytes(f.read_bytes())
print(f"Reports written to {out_dir} and {latest_dir}")

if run.health_status == "fail":
    failed = "; ".join(f"{c['label']}: {c['detail']}" for c in run.health if c["status"] == "fail")
    raise RuntimeError(f"Data checks failed, tables not updated: {failed}")

for suffix, rows in (("scorecard", scorecard_rows(run.result, config)), ("worklist", worklist_rows(run.result)),
                     ("runs", [run_log_row(run, source)])):
    table = f"{w['output_prefix']}_{suffix}"
    n = dbx.spark_write_table(spark, table, rows, as_of)
    print(f"Wrote {n} rows to {table} for {as_of}")

# COMMAND ----------

display(spark.table(f"{w['output_prefix']}_worklist").where(f"as_of = DATE'{as_of.isoformat()}'").orderBy("rank"))

# COMMAND ----------

# Headline figures become the task's output, visible in the job run page and to downstream tasks.
sm = run.result.summary
dbutils.notebook.exit(json.dumps({
    "as_of": as_of.isoformat(),
    "data_health": run.health_status,
    "backtest": (run.backtest or {}).get("verdict"),
    "fingerprint": run.fingerprint,
    "customers": sm["customers"],
    "total_outstanding": sm["total_outstanding"],
    "overdue_pct": sm["overdue_pct"],
    "grades": {g: d["customers"] for g, d in sm["by_grade"].items()},
    "collection_tiers": sm["collection_tiers"],
    "previous_as_of": prev_as_of,
    "changes": len(run.changes or []),
    "reports": str(out_dir),
}))
