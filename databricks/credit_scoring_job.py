# Databricks notebook source
# MAGIC %md
# MAGIC # Credit-risk scoring job
# MAGIC Reads the debtor ledger from Unity Catalog, scores every customer, and writes:
# MAGIC * `<output_prefix>_scorecard` and `<output_prefix>_worklist` Delta tables, one set of rows per `as_of`, so history accumulates
# MAGIC * `dashboard.html` and the CSV/Markdown reports to a Volume, one folder per `as_of`
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

from scoring_engine import engine
from scoring_engine.config import load_config
from scoring_engine.dashboard import write_dashboard
from scoring_engine.loader import merge_customers, parse_date, rows_to_customers, rows_to_invoices
from scoring_engine.report import scorecard_rows, worklist_rows, write_outputs
from scoring_engine.sources import databricks as dbx

w = {k: dbutils.widgets.get(k).strip() for k in
     ["invoices_table", "customers_table", "output_prefix", "output_volume", "as_of", "policy_json", "lookback_months", "currency"]}

if not w["as_of"]:
    as_of = date.today().replace(day=1) - timedelta(days=1)  # last day of previous month
elif w["as_of"].lower() == "today":
    as_of = date.today()
else:
    as_of = parse_date(w["as_of"])
config = load_config(overrides=json.loads(w["policy_json"]) if w["policy_json"] else None)
print(f"Scoring as at {as_of} from {w['invoices_table']} (engine at {repo_root})")

# COMMAND ----------

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
customers = merge_customers(invoices, rows_to_customers(data["customers"], w["customers_table"] or "customers"))
print(f"Loaded {len(invoices):,} invoices for {len(customers):,} customers")

result = engine.run(invoices, customers, as_of, config)
print(json.dumps(result.summary, indent=2, default=str))

# COMMAND ----------

for suffix, rows in (("scorecard", scorecard_rows(result, config)), ("worklist", worklist_rows(result))):
    table = f"{w['output_prefix']}_{suffix}"
    n = dbx.spark_write_table(spark, table, rows, as_of)
    print(f"Wrote {n} rows to {table} for {as_of}")

# Reports go to a Volume, one folder per as_of date.
out_dir = Path(w["output_volume"]) / as_of.isoformat()
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    write_outputs(result, config, tmp)
    write_dashboard(result, config, tmp / "dashboard.html", source=w["invoices_table"], currency=w["currency"])
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in tmp.iterdir():
        (out_dir / f.name).write_bytes(f.read_bytes())
print(f"Reports written to {out_dir}")

# COMMAND ----------

display(spark.table(f"{w['output_prefix']}_worklist").where(f"as_of = DATE'{as_of.isoformat()}'").orderBy("rank"))

# COMMAND ----------

# Headline figures become the task's output, visible in the job run page and to downstream tasks.
sm = result.summary
dbutils.notebook.exit(json.dumps({
    "as_of": as_of.isoformat(),
    "customers": sm["customers"],
    "total_outstanding": sm["total_outstanding"],
    "overdue_pct": sm["overdue_pct"],
    "grades": {g: d["customers"] for g, d in sm["by_grade"].items()},
    "collection_tiers": sm["collection_tiers"],
    "reports": str(out_dir),
}))
