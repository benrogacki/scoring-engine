"""Backtest, data health, change detection, the credit feed and the CLI around them."""
import copy
import csv
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from scoring_engine.backtest import auc_score, run_backtest, went_bad
from scoring_engine.changes import diff_scorecards
from scoring_engine.cli import main
from scoring_engine.config import DEFAULT_CONFIG
from scoring_engine.feed import SCHEMA
from scoring_engine.health import check_data, overall
from scoring_engine.loader import merge_customers, read_customers, read_ledger
from scoring_engine.models import Customer, Invoice

REPO = Path(__file__).resolve().parents[1]
LEDGER, CUSTOMERS = REPO / "examples" / "ledger.csv", REPO / "examples" / "customers.csv"
AS_OF = date(2026, 9, 30)


def cfg():
    return copy.deepcopy(DEFAULT_CONFIG)


def inv(iid, cid, issued_days_ago, due_days, amount=1000.0, paid_days_after_due=None):
    issued = AS_OF - timedelta(days=issued_days_ago)
    due = issued + timedelta(days=due_days)
    paid = None if paid_days_after_due is None else due + timedelta(days=paid_days_after_due)
    return Invoice(iid, cid, issued, due, amount, amount if paid else 0.0, paid)


def by_id(checks):
    return {c["id"]: c for c in checks}


class BacktestTests(unittest.TestCase):
    def test_went_bad_window(self):
        t = AS_OF - timedelta(days=120)
        # due at t+10, unpaid: crosses 60 dpd at t+70, inside a 90-day horizon
        unpaid = [Invoice("1", "X", t - timedelta(days=20), t + timedelta(days=10), 100.0)]
        self.assertTrue(went_bad(unpaid, t, 90, 60))
        # paid 30 days late: never crosses 60
        late = [Invoice("1", "X", t - timedelta(days=20), t + timedelta(days=10), 100.0, 100.0, t + timedelta(days=40))]
        self.assertFalse(went_bad(late, t, 90, 60))
        # already 60+ past due before t: crossed before the window, not counted
        old = [Invoice("1", "X", t - timedelta(days=120), t - timedelta(days=90), 100.0)]
        self.assertFalse(went_bad(old, t, 90, 60))

    def test_auc(self):
        self.assertEqual(auc_score([10, 20], [80, 90]), 1.0)
        self.assertEqual(auc_score([50], [50]), 0.5)
        self.assertIsNone(auc_score([], [1]))

    def test_sample_ledger_is_evidenced(self):
        invoices = read_ledger(LEDGER)
        customers = merge_customers(invoices, read_customers(CUSTOMERS))
        bt = run_backtest(invoices, customers, AS_OF, cfg())
        self.assertEqual(bt.verdict, "evidenced")
        self.assertGreaterEqual(bt.auc, 0.7)
        self.assertEqual(len(bt.points), 4)
        self.assertGreater(bt.by_grade["E"]["bad_rate"], bt.by_grade["A"]["bad_rate"])

    def test_short_ledger_is_insufficient(self):
        invoices = [inv("1", "X", 60, 30)]
        bt = run_backtest(invoices, {"X": Customer("X", "X")}, AS_OF, cfg())
        self.assertEqual(bt.verdict, "insufficient data")
        self.assertIn("too short", bt.note)


class HealthTests(unittest.TestCase):
    def test_clean_sample(self):
        invoices = read_ledger(LEDGER)
        checks = check_data(invoices, read_customers(CUSTOMERS), AS_OF, cfg())
        self.assertEqual(overall(checks), "ok")

    def test_problems_are_flagged(self):
        invoices = [inv("1", "A", 200, 30), inv("1", "A", 190, 30), inv("2", "B", 100, -5)]
        checks = by_id(check_data(invoices, {"A": Customer("A", "A")}, AS_OF, cfg()))
        self.assertEqual(checks["duplicates"]["status"], "warn")
        self.assertEqual(checks["dates"]["status"], "warn")
        self.assertEqual(checks["freshness"]["status"], "warn")  # newest invoice 100 days old
        self.assertEqual(checks["master"]["status"], "warn")      # B missing from master
        self.assertIn("B", checks["master"]["detail"])

    def test_control_total(self):
        invoices = [inv("1", "A", 20, 30, amount=1000.0)]
        master = {"A": Customer("A", "A")}
        self.assertEqual(by_id(check_data(invoices, master, AS_OF, cfg(), control_total=1000.0))["control_total"]["status"], "ok")
        bad = by_id(check_data(invoices, master, AS_OF, cfg(), control_total=1500.0))["control_total"]
        self.assertEqual(bad["status"], "fail")
        self.assertIn("-500.00", bad["detail"])

    def test_empty_extract_fails(self):
        self.assertEqual(overall(check_data([], {}, AS_OF, cfg())), "fail")


class ChangesTests(unittest.TestCase):
    def row(self, cid, grade, tier="", util="50", action="Maintain", score="70"):
        return {"customer_id": cid, "customer_name": cid, "grade": grade, "composite_score": score,
                "collection_tier": tier, "limit_utilisation_pct": util, "limit_action": action,
                "outstanding": "1000", "overdue": "500", "oldest_days_overdue": "95", "credit_limit": "2000",
                "recommended_limit": "2000"}

    def test_kinds_and_order(self):
        old = {"A": self.row("A", "B"), "B": self.row("B", "C", tier="P2"), "C": self.row("C", "A"), "D": self.row("D", "A")}
        new = {"A": self.row("A", "C"), "B": self.row("B", "C", tier="P1"), "C": self.row("C", "A", util="120"),
               "E": self.row("E", "B")}
        kinds = [(c["kind"], c["customer_id"]) for c in diff_scorecards(old, new)]
        self.assertEqual(kinds, [("escalated", "B"), ("downgrade", "A"), ("over_limit", "C"), ("new", "E"), ("gone", "D")])

    def test_limit_action_ignores_suffixes(self):
        old = {"A": self.row("A", "B", action="Maintain - currently over limit")}
        new = {"A": self.row("A", "B", action="Maintain (concentration cap)")}
        self.assertEqual(diff_scorecards(old, new), [])


class CliRunTests(unittest.TestCase):
    def run_cli(self, *extra, out):
        return main(["run", "--ledger", str(LEDGER), "--customers", str(CUSTOMERS), "--out", str(out), *extra])

    def test_full_run_with_previous(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.assertEqual(self.run_cli("--as-of", "2026-08-31", out=d / "aug"), 0)
            summary = d / "summary.md"
            self.assertEqual(self.run_cli("--as-of", "2026-09-30", "--previous", str(d / "aug"),
                                          "--job-summary", str(summary), out=d / "sep"), 0)
            feed = json.loads((d / "sep" / "credit_feed.json").read_text())
            self.assertEqual(feed["schema"], SCHEMA)
            self.assertEqual(feed["data_health"], "ok")
            self.assertEqual(feed["backtest"]["verdict"], "evidenced")
            self.assertEqual(len(feed["customers"]), 36)
            holds = [c for c in feed["customers"] if c["credit_hold"]]
            self.assertTrue(all(c["grade"] == "E" or c["oldest_days_overdue"] > 90 for c in holds))
            self.assertEqual(feed["portfolio"]["credit_holds"], len(holds))
            changes = json.loads((d / "sep" / "changes.json").read_text())
            self.assertEqual(changes["previous_as_of"], "2026-08-31")
            self.assertIn("downgrade", changes["counts"])
            self.assertEqual(len(feed["changes"]), len(changes["changes"]))
            fp = (d / "sep" / "data_fingerprint.txt").read_text().strip()
            self.assertEqual(fp, feed["fingerprint"])
            page = (d / "sep" / "dashboard.html").read_text()
            self.assertIn(fp, page)
            self.assertIn('"previous_as_of":"2026-08-31"', page)
            md = (d / "sep" / "portfolio_summary.md").read_text()
            self.assertIn("## Backtest", md)
            self.assertIn("## Changes since the last run", md)
            # The CI job summary is aggregate-only: no customer names.
            text = summary.read_text()
            with open(CUSTOMERS, newline="") as fh:
                names = [r["customer_name"] for r in csv.DictReader(fh)]
            self.assertFalse([n for n in names if n in text])

    def test_same_data_same_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.run_cli("--as-of", "2026-09-30", "--no-backtest", out=d / "a")
            self.run_cli("--as-of", "2026-09-30", "--no-backtest", out=d / "b")
            self.assertEqual((d / "a" / "data_fingerprint.txt").read_text(), (d / "b" / "data_fingerprint.txt").read_text())

    def test_strict_fails_on_bad_reconciliation(self):
        with tempfile.TemporaryDirectory() as d:
            rc = self.run_cli("--as-of", "2026-09-30", "--no-backtest", "--control-total", "1", "--strict", out=Path(d))
            self.assertEqual(rc, 1)
            self.assertEqual(json.loads((Path(d) / "data_health.json").read_text())["status"], "fail")

    def test_failed_checks_never_write_tables(self):
        from unittest import mock
        from scoring_engine.sources import databricks as dbx
        with tempfile.TemporaryDirectory() as d, mock.patch.object(dbx, "connect") as connect:
            rc = self.run_cli("--as-of", "2026-09-30", "--no-backtest", "--control-total", "1",
                              "--write-table-prefix", "main.finance.credit_risk", out=Path(d))
            self.assertEqual(rc, 0)
            connect.assert_not_called()

    def test_probe_and_changes_commands(self):
        self.assertEqual(main(["probe", "--ledger", str(LEDGER), "--customers", str(CUSTOMERS), "--as-of", "2026-09-30"]), 0)
        self.assertEqual(main(["probe", "--ledger", str(LEDGER), "--as-of", "2026-09-30", "--control-total", "5"]), 1)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.run_cli("--as-of", "2026-08-31", "--no-backtest", out=d / "aug")
            self.run_cli("--as-of", "2026-09-30", "--no-backtest", out=d / "sep")
            self.assertEqual(main(["changes", str(d / "aug"), str(d / "sep")]), 0)


if __name__ == "__main__":
    unittest.main()
