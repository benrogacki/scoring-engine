# Databricks notebook source
# MAGIC %md
# MAGIC # Credit-risk scoring job
# MAGIC Reads the debtor ledger from Unity Catalog, scores every customer, and writes:
# MAGIC * `<output_prefix>_scorecard` and `<output_prefix>_worklist` Delta tables (one set of rows per `as_of`, so history accumulates)
# MAGIC * `dashboard.html` and the CSV/Markdown reports to a Volume
# MAGIC
# MAGIC Run it from a Git folder containing this repo; the engine is pure Python, so nothing needs installing.
# MAGIC Schedule it as a Job (e.g. 06:00 on the 1st working day) with the parameters below.

# COMMAND ----------

dbutils.widgets.text("invoices_table", "main.finance.credit_ar_invoices", "Invoices table/view")
dbutils.widgets.text("customers_table", "main.finance.credit_customers", "Customers table/view (optional)")
dbutils.widgets.text("output_prefix", "main.finance.credit_risk", "Output table prefix")
dbutils.widgets.text("output_volume", "/Volumes/main/finance/reports/credit_scoring", "Folder for reports")
dbutils.widgets.text("as_of", "", "Scoring date YYYY-MM-DD (blank = today)")
dbutils.widgets.text("policy_json", "", "Policy overrides as JSON (optional)")
dbutils.widgets.text("lookback_months", "15", "Months of invoices to read")
dbutils.widgets.text("currency", "", "Currency symbol for the dashboard")

# COMMAND ----------

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

# Make the repo importable when this notebook runs from a Databricks Git folder.
repo_root = str(Path(os.getcwd()).parent) if Path(os.getcwd()).name == "databricks" else os.getcwd()
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
as_of = parse_date(w["as_of"]) or date.today()
config = load_config(overrides=json.loads(w["policy_json"]) if w["policy_json"] else None)

# COMMAND ----------

data = dbx.fetch(
    conn=None,
    spark=spark,
    invoices_table=w["invoices_table"],
    customers_table=w["customers_table"] or None,
    lookback_months=int(w["lookback_months"] or 15),
)
invoices = rows_to_invoices(data["invoices"], w["invoices_table"])
customers = merge_customers(invoices, rows_to_customers(data["customers"], w["customers_table"]))
print(f"Loaded {len(invoices):,} invoices for {len(customers):,} customers")

result = engine.run(invoices, customers, as_of, config)
print(json.dumps(result.summary, indent=2, default=str))

# COMMAND ----------

for suffix, rows in (("scorecard", scorecard_rows(result, config)), ("worklist", worklist_rows(result))):
    table = f"{w['output_prefix']}_{suffix}"
    n = dbx.spark_write_table(spark, table, rows, as_of)
    print(f"Wrote {n} rows to {table} for {as_of}")

# Reports go to a Volume, one folder per run.
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
