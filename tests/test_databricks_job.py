"""Runs databricks/credit_scoring_job.py end to end with stand-ins for spark and dbutils."""
import csv
import json
import os
import re
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NOTEBOOK = REPO / "databricks" / "credit_scoring_job.py"
JOB = REPO / "databricks" / "credit_scoring_job.json"


class NotebookExit(Exception):
    pass


class FakeDbutils:
    def __init__(self, params):
        self.params = params
        self.widgets = self
        self.notebook = self

    def text(self, name, default, label=None):
        self.params.setdefault(name, default)

    def get(self, name):
        return self.params[name]

    def exit(self, value):
        raise NotebookExit(value)


class Row(dict):
    def asDict(self):
        return dict(self)


class FakeFrame:
    def __init__(self, spark, rows=None, schema=None):
        self.spark, self.rows, self.schema = spark, rows or [], schema
        self.write = self
        self._mode = "errorifexists"

    def collect(self):
        return self.rows

    def mode(self, m):
        self._mode = m
        return self

    def option(self, *a):
        return self

    def saveAsTable(self, name):
        cols = [part.strip().split(" ")[0].strip("`") for part in self.schema.split(",")]
        rows = [Row(zip(cols, values)) for values in self.rows]
        self.spark.saved.append((name, self._mode, self.schema, self.rows))
        if self._mode == "append" and name in self.spark.tables:
            self.spark.tables[name].extend(rows)
        else:
            self.spark.tables[name] = rows

    def where(self, *a):
        return self

    def orderBy(self, *a):
        return self


class FakeSpark:
    """Enough of a SparkSession for the notebook: reads the source views, stores written tables."""

    def __init__(self, ledger, customers):
        self.ledger, self.customers = ledger, customers
        self.queries, self.saved, self.tables = [], [], {}
        self.catalog = self

    def tableExists(self, name):
        return name in self.tables

    def sql(self, q):
        self.queries.append(q)
        if "credit_ar_invoices" in q:
            return FakeFrame(self, [Row(r) for r in self.ledger])
        if "credit_customers" in q:
            return FakeFrame(self, [Row(r) for r in self.customers])
        m = re.match(r"(SELECT max\(as_of\) AS d|SELECT \*|DELETE) FROM (\S+) WHERE as_of (<|=) DATE'([\d-]+)'", q)
        if m:
            kind, table, op, d = m.groups()
            d = date.fromisoformat(d)
            rows = self.tables.get(table, [])
            if kind.startswith("DELETE"):
                self.tables[table] = [r for r in rows if r["as_of"] != d]
                return FakeFrame(self)
            if kind.startswith("SELECT max"):
                earlier = [r["as_of"] for r in rows if r["as_of"] < d]
                return FakeFrame(self, [Row(d=max(earlier) if earlier else None)])
            return FakeFrame(self, [r for r in rows if r["as_of"] == d])
        return FakeFrame(self)

    def createDataFrame(self, rows, schema=None):
        return FakeFrame(self, rows, schema)

    def table(self, name):
        return FakeFrame(self)


def read_csv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


class DatabricksJobTests(unittest.TestCase):
    def run_notebook(self, params, ledger=None, spark=None):
        ledger = read_csv(REPO / "examples" / "ledger.csv") if ledger is None else ledger
        spark = spark or FakeSpark(ledger, read_csv(REPO / "examples" / "customers.csv"))
        dbutils = FakeDbutils(dict(params))
        cwd = os.getcwd()
        os.chdir(REPO / "databricks")  # Databricks runs a notebook from its own folder
        try:
            exec(compile(NOTEBOOK.read_text(), str(NOTEBOOK), "exec"),
                 {"spark": spark, "dbutils": dbutils, "display": lambda df: None, "__name__": "__main__"})
        except NotebookExit as done:
            return spark, json.loads(str(done))
        finally:
            os.chdir(cwd)
        self.fail("notebook did not call dbutils.notebook.exit")

    def test_end_to_end_on_sample_ledger(self):
        with tempfile.TemporaryDirectory() as vol:
            spark, out = self.run_notebook({"output_volume": vol, "as_of": "2026-09-30", "currency": "£"})
            self.assertEqual(out["as_of"], "2026-09-30")
            self.assertEqual(out["customers"], 36)
            self.assertEqual(sum(out["grades"].values()), 36)
            names = [s[0] for s in spark.saved]
            self.assertEqual(names, ["main.finance.credit_risk_scorecard", "main.finance.credit_risk_worklist",
                                     "main.finance.credit_risk_runs"])
            self.assertEqual(out["data_health"], "ok")
            self.assertEqual(out["backtest"], "evidenced")
            self.assertIsNone(out["previous_as_of"])
            scorecard = spark.saved[0]
            self.assertTrue(scorecard[2].startswith("as_of DATE, `customer_id` STRING"))
            self.assertEqual(len(scorecard[3]), 36)
            files = sorted(p.name for p in (Path(vol) / "2026-09-30").iterdir())
            self.assertEqual(files, ["backtest.json", "changes.json", "collections_worklist.csv", "credit_feed.json",
                                     "dashboard.html", "data_fingerprint.txt", "data_health.json",
                                     "portfolio_summary.json", "portfolio_summary.md", "scorecard.csv"])
            self.assertEqual(sorted(p.name for p in (Path(vol) / "latest").iterdir()), files)
            self.assertIn("-15)", spark.queries[0])

    def test_rerun_same_date_replaces_rows(self):
        with tempfile.TemporaryDirectory() as vol:
            params = {"output_volume": vol, "as_of": "2026-09-30"}
            spark, _ = self.run_notebook(params)
            spark, _ = self.run_notebook(params, spark=spark)
            deletes = [q for q in spark.queries if q.startswith("DELETE")]
            self.assertEqual(len(deletes), 3)
            self.assertIn("as_of = DATE'2026-09-30'", deletes[0])
            self.assertEqual(len(spark.tables["main.finance.credit_risk_scorecard"]), 36)
            self.assertEqual(len(spark.tables["main.finance.credit_risk_runs"]), 1)

    def test_compares_with_previous_run_in_the_table(self):
        with tempfile.TemporaryDirectory() as vol:
            spark, _ = self.run_notebook({"output_volume": vol, "as_of": "2026-08-31"})
            spark, out = self.run_notebook({"output_volume": vol, "as_of": "2026-09-30"}, spark=spark)
            self.assertEqual(out["previous_as_of"], "2026-08-31")
            self.assertGreater(out["changes"], 0)
            log = spark.tables["main.finance.credit_risk_runs"]
            self.assertEqual(len(log), 2)
            sep = [r for r in log if r["as_of"] == date(2026, 9, 30)][0]
            self.assertEqual(sep["previous_as_of"], "2026-08-31")
            self.assertEqual(sep["changes"], out["changes"])
            changes = json.loads((Path(vol) / "2026-09-30" / "changes.json").read_text())
            self.assertIn("Pinnacle Group", [c["customer_name"] for c in changes["changes"]])

    def test_failed_data_checks_leave_tables_untouched(self):
        with tempfile.TemporaryDirectory() as vol:
            spark, _ = self.run_notebook({"output_volume": vol, "as_of": "2026-09-30"})
            before = len(spark.saved)
            with self.assertRaisesRegex(RuntimeError, "Data checks failed, tables not updated"):
                self.run_notebook({"output_volume": vol, "as_of": "2026-09-30", "control_total": "1,000,000"},
                                  spark=spark)
            self.assertEqual(len(spark.saved), before)
            health = json.loads((Path(vol) / "latest" / "data_health.json").read_text())
            self.assertEqual(health["status"], "fail")

    def test_blank_as_of_means_last_month_end(self):
        with tempfile.TemporaryDirectory() as vol:
            _, out = self.run_notebook({"output_volume": vol})
            expected = date.today().replace(day=1) - timedelta(days=1)
            self.assertEqual(out["as_of"], expected.isoformat())

    def test_empty_ledger_fails_the_run(self):
        with tempfile.TemporaryDirectory() as vol:
            with self.assertRaisesRegex(RuntimeError, "No invoices returned"):
                self.run_notebook({"output_volume": vol, "as_of": "2026-09-30"}, ledger=[])

    def test_job_definition_matches_notebook(self):
        job = json.loads(JOB.read_text())
        task = job["tasks"][0]["notebook_task"]
        self.assertEqual(task["source"], "GIT")
        self.assertTrue((REPO / (task["notebook_path"] + ".py")).exists())
        widgets = set()
        for line in NOTEBOOK.read_text().splitlines():
            if line.startswith("dbutils.widgets.text("):
                widgets.add(line.split('"')[1])
        self.assertEqual(set(task["base_parameters"]), widgets)


if __name__ == "__main__":
    unittest.main()
