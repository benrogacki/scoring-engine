"""Runs databricks/credit_scoring_job.py end to end with stand-ins for spark and dbutils."""
import csv
import json
import os
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
        self.spark.saved.append((name, self._mode, self.schema, self.rows))
        self.spark.existing.add(name)

    def where(self, *a):
        return self

    def orderBy(self, *a):
        return self


class FakeSpark:
    def __init__(self, ledger, customers):
        self.ledger, self.customers = ledger, customers
        self.queries, self.saved, self.existing = [], [], set()
        self.catalog = self

    def tableExists(self, name):
        return name in self.existing

    def sql(self, q):
        self.queries.append(q)
        if "credit_ar_invoices" in q:
            return FakeFrame(self, [Row(r) for r in self.ledger])
        if "credit_customers" in q:
            return FakeFrame(self, [Row(r) for r in self.customers])
        return FakeFrame(self)

    def createDataFrame(self, rows, schema=None):
        return FakeFrame(self, rows, schema)

    def table(self, name):
        return FakeFrame(self)


def read_csv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


class DatabricksJobTests(unittest.TestCase):
    def run_notebook(self, params, ledger=None):
        ledger = read_csv(REPO / "examples" / "ledger.csv") if ledger is None else ledger
        spark = FakeSpark(ledger, read_csv(REPO / "examples" / "customers.csv"))
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
            self.assertEqual(names, ["main.finance.credit_risk_scorecard", "main.finance.credit_risk_worklist"])
            scorecard = spark.saved[0]
            self.assertTrue(scorecard[2].startswith("as_of DATE, `customer_id` STRING"))
            self.assertEqual(len(scorecard[3]), 36)
            files = sorted(p.name for p in (Path(vol) / "2026-09-30").iterdir())
            self.assertEqual(files, ["collections_worklist.csv", "dashboard.html", "portfolio_summary.json",
                                     "portfolio_summary.md", "scorecard.csv"])
            self.assertIn("-15)", spark.queries[0])

    def test_rerun_same_date_replaces_rows(self):
        with tempfile.TemporaryDirectory() as vol:
            params = {"output_volume": vol, "as_of": "2026-09-30"}
            spark = FakeSpark(read_csv(REPO / "examples" / "ledger.csv"), read_csv(REPO / "examples" / "customers.csv"))
            spark.existing.add("main.finance.credit_risk_scorecard")
            spark.existing.add("main.finance.credit_risk_worklist")
            # Reuse the fake with tables already present.
            dbutils = FakeDbutils(dict(params))
            cwd = os.getcwd()
            os.chdir(REPO / "databricks")
            try:
                with self.assertRaises(NotebookExit):
                    exec(compile(NOTEBOOK.read_text(), str(NOTEBOOK), "exec"),
                         {"spark": spark, "dbutils": dbutils, "display": lambda df: None})
            finally:
                os.chdir(cwd)
            deletes = [q for q in spark.queries if q.startswith("DELETE")]
            self.assertEqual(len(deletes), 2)
            self.assertIn("as_of = DATE'2026-09-30'", deletes[0])
            self.assertTrue(all(mode == "append" for _, mode, _, _ in spark.saved))

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
