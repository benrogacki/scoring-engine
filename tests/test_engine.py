import copy
import csv
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from scoring_engine.cli import main
from scoring_engine.collection import prioritise_collections
from scoring_engine.config import DEFAULT_CONFIG, load_config
from scoring_engine.features import ageing_bucket, build_features
from scoring_engine.limits import recommend_limit
from scoring_engine.loader import LedgerError, parse_amount, read_ledger
from scoring_engine.models import Customer, Invoice
from scoring_engine.scoring import score_customer

AS_OF = date(2026, 9, 30)


def cfg():
    return copy.deepcopy(DEFAULT_CONFIG)


def history(cid, days_late, n=10, amount=1000.0, terms=30, start_days_ago=360, open_last=0):
    """Monthly invoices paid ``days_late`` after due; the last ``open_last`` stay unpaid."""
    invoices = []
    for i in range(n):
        inv_date = AS_OF - timedelta(days=start_days_ago - i * 30)
        due = inv_date + timedelta(days=terms)
        paid = due + timedelta(days=days_late)
        is_open = i >= n - open_last or paid > AS_OF
        invoices.append(
            Invoice(
                invoice_id=f"{cid}-{i}",
                customer_id=cid,
                invoice_date=inv_date,
                due_date=due,
                amount=amount,
                amount_paid=0.0 if is_open else amount,
                paid_date=None if is_open else paid,
            )
        )
    return invoices


def score_one(invoices, customers, cid, config=None):
    config = config or cfg()
    features = build_features(invoices, customers, AS_OF, config)
    s = score_customer(customers[cid], features[cid], config)
    recommend_limit(s, config)
    return s


class LoaderTests(unittest.TestCase):
    def test_parse_amount_formats(self):
        self.assertEqual(parse_amount("£1,234.50"), 1234.5)
        self.assertEqual(parse_amount("(200)"), -200)
        self.assertIsNone(parse_amount(""))

    def test_aliases_and_implied_full_payment(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "l.csv"
            p.write_text(
                "Invoice No,Account,Document Date,Due Date,Invoice Amount,Payment Date\n"
                "1,A1,01/08/2026,31/08/2026,\"1,000.00\",2026-09-05\n"
            )
            (inv,) = read_ledger(p)
        self.assertEqual(inv.customer_id, "A1")
        self.assertEqual(inv.amount_paid, 1000.0)
        self.assertTrue(inv.is_settled)
        self.assertEqual(inv.days_late_paid(), 5)

    def test_missing_column_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "l.csv"
            p.write_text("invoice_id,customer_id,amount\n1,A,10\n")
            with self.assertRaisesRegex(LedgerError, "invoice_date"):
                read_ledger(p)


class FeatureTests(unittest.TestCase):
    def test_bucket_boundaries(self):
        self.assertEqual([ageing_bucket(d) for d in (0, 1, 30, 31, 60, 61, 90, 91)],
                         ["current", "1_30", "1_30", "31_60", "31_60", "61_90", "61_90", "90_plus"])

    def test_unpaid_overdue_counts_as_late_not_thin_file(self):
        invs = history("X", days_late=0, n=4, start_days_ago=200, open_last=4)
        f = build_features(invs, {"X": Customer("X", "X")}, AS_OF, cfg())["X"]
        self.assertEqual(f.paid_invoice_count, 0)
        self.assertIsNotNone(f.weighted_avg_days_late)
        self.assertGreater(f.weighted_avg_days_late, 60)
        self.assertEqual(f.on_time_rate, 0.0)

    def test_payment_after_as_of_is_still_open(self):
        inv = Invoice("1", "X", AS_OF - timedelta(days=60), AS_OF - timedelta(days=30), 500.0, 500.0,
                      paid_date=AS_OF + timedelta(days=3))
        f = build_features([inv], {"X": Customer("X", "X")}, AS_OF, cfg())["X"]
        self.assertEqual(f.outstanding, 500.0)
        self.assertEqual(f.ageing["1_30"], 500.0)

    def test_share_and_utilisation(self):
        invs = history("A", 0, n=2, start_days_ago=40) + history("B", 0, n=2, amount=3000, start_days_ago=40)
        customers = {"A": Customer("A", "A", credit_limit=1000), "B": Customer("B", "B")}
        f = build_features(invs, customers, AS_OF, cfg())
        self.assertAlmostEqual(f["A"].share_of_portfolio + f["B"].share_of_portfolio, 1.0)
        self.assertAlmostEqual(f["A"].limit_utilisation, f["A"].outstanding / 1000)
        self.assertIsNone(f["B"].limit_utilisation)


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.customers = {
            "GOOD": Customer("GOOD", "Good Co", credit_limit=5000),
            "BAD": Customer("BAD", "Bad Co", credit_limit=2000),
            "FILLER": Customer("FILLER", "Filler", credit_limit=100000),
        }
        self.invoices = (
            history("GOOD", 0)
            + history("BAD", 70, n=10, open_last=5)
            + history("FILLER", 0, amount=20000, start_days_ago=50, n=2)
        )

    def test_prompt_payer_scores_a_and_non_payer_e(self):
        good = score_one(self.invoices, self.customers, "GOOD")
        bad = score_one(self.invoices, self.customers, "BAD")
        self.assertEqual(good.grade, "A")
        self.assertEqual(bad.grade, "E")
        self.assertEqual(bad.limit_action, "Suspend credit (cash with order)")
        self.assertTrue(any("90+" in r for r in bad.reasons))

    def test_thin_file_uses_neutral_payment_score(self):
        customers = {"NEW": Customer("NEW", "New")}
        inv = Invoice("1", "NEW", AS_OF - timedelta(days=5), AS_OF + timedelta(days=25), 1000.0)
        s = score_one([inv], customers, "NEW")
        self.assertEqual(s.payment_score, DEFAULT_CONFIG["payment_history"]["thin_file_score"])
        self.assertIn("Thin file", s.reasons[0])

    def test_90_plus_arrears_caps_grade(self):
        # Excellent history but one large invoice 120 days overdue.
        invs = history("G", 0, amount=10000, n=12, start_days_ago=350) + [
            Invoice("old", "G", AS_OF - timedelta(days=150), AS_OF - timedelta(days=120), 3000.0)
        ]
        s = score_one(invs + self.invoices, {**self.customers, "G": Customer("G", "G", 50000)}, "G")
        self.assertGreaterEqual(s.composite_score, 65)  # would be A/B on score alone
        self.assertEqual(s.grade, "C")
        self.assertTrue(any("capped at C" in r for r in s.reasons))

    def test_weights_change_composite(self):
        config = cfg()
        config["weights"] = {"payment": 1.0, "ageing": 0.0, "concentration": 0.0}
        s = score_one(self.invoices, self.customers, "GOOD", config)
        self.assertEqual(s.composite_score, s.payment_score)


class LimitTests(unittest.TestCase):
    def test_increase_capped_and_only_for_good_grades(self):
        customers = {"G": Customer("G", "G", credit_limit=10000), "F": Customer("F", "F", credit_limit=1e6)}
        invs = history("G", 0, amount=10000) + history("F", 0, amount=200000, n=2, start_days_ago=40)
        s = score_one(invs, customers, "G")
        self.assertEqual(s.grade, "A")
        self.assertEqual(s.recommended_limit, 15000)  # +50% max per review
        self.assertTrue(s.limit_action.startswith("Increase"))

        config = cfg()
        config["credit_limits"]["increase_allowed_grades"] = []
        s = score_one(invs, customers, "G", config)
        self.assertTrue(s.limit_action.startswith("Maintain"))

    def test_set_limit_when_none_on_file(self):
        customers = {"N": Customer("N", "N"), "F": Customer("F", "F", credit_limit=1e6)}
        invs = history("N", 0, amount=3000) + history("F", 0, amount=100000, n=2, start_days_ago=40)
        s = score_one(invs, customers, "N")
        self.assertEqual(s.limit_action, "Set limit")
        self.assertGreater(s.recommended_limit, 0)

    def test_concentration_blocks_increase(self):
        customers = {"BIG": Customer("BIG", "Big", credit_limit=1000)}
        s = score_one(history("BIG", 0, amount=5000, start_days_ago=290), customers, "BIG")
        self.assertEqual(s.features.share_of_portfolio, 1.0)
        self.assertIn("concentration cap", s.limit_action)
        self.assertEqual(s.recommended_limit, 1000)


class CollectionTests(unittest.TestCase):
    def test_tiers_and_order(self):
        customers = {c: Customer(c, c, credit_limit=100000) for c in ("OLD", "MID", "FRESH", "CLEAN")}
        # Every customer has a clean year of history and a large current balance,
        # so tiering is driven by the age of the single overdue item.
        invs = [i for c in customers for i in history(c, 0, amount=10000, n=12, start_days_ago=350)]
        invs += [
            Invoice("1", "OLD", AS_OF - timedelta(days=150), AS_OF - timedelta(days=120), 1000.0),
            Invoice("2", "MID", AS_OF - timedelta(days=100), AS_OF - timedelta(days=70), 1000.0),
            Invoice("3", "FRESH", AS_OF - timedelta(days=40), AS_OF - timedelta(days=10), 1000.0),
        ]
        config = cfg()
        features = build_features(invs, customers, AS_OF, config)
        scores = [score_customer(customers[c], f, config) for c, f in features.items()]
        worklist = prioritise_collections(scores, config)
        self.assertEqual([s.customer.customer_id for s in worklist], ["OLD", "MID", "FRESH"])
        self.assertEqual([s.collection_tier for s in worklist], ["P1", "P2", "P4"])
        self.assertEqual([s.collection_rank for s in worklist], [1, 2, 3])


class ConfigTests(unittest.TestCase):
    def test_partial_override_and_validation(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text(json.dumps({"grace_days": 0, "ageing": {"disputed_penalty": 0}}))
            config = load_config(p)
            self.assertEqual(config["grace_days"], 0)
            self.assertEqual(config["ageing"]["bucket_weights"]["90_plus"], 1.0)  # untouched default
            p.write_text(json.dumps({"weights": {"payment": 0.9}}))
            with self.assertRaisesRegex(ValueError, "sum to 1.0"):
                load_config(p)

    def test_shipped_config_matches_defaults(self):
        shipped = Path(__file__).resolve().parents[1] / "config" / "default.json"
        self.assertEqual(json.loads(shipped.read_text()), DEFAULT_CONFIG)


class EndToEndTests(unittest.TestCase):
    def test_cli_sample_then_run(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.assertEqual(main(["sample", "--out", str(d), "--as-of", "2026-09-30"]), 0)
            rc = main(["run", "--ledger", str(d / "ledger.csv"), "--customers", str(d / "customers.csv"),
                       "--as-of", "2026-09-30", "--out", str(d / "out")])
            self.assertEqual(rc, 0)
            rows = list(csv.DictReader(open(d / "out" / "scorecard.csv")))
            self.assertEqual(len(rows), 36)
            grades = {r["grade"] for r in rows}
            self.assertTrue({"A", "E"} <= grades)
            summary = json.loads((d / "out" / "portfolio_summary.json").read_text())
            ageing_total = sum(summary["ageing"].values())
            self.assertAlmostEqual(ageing_total, summary["total_outstanding"], places=0)
            self.assertTrue((d / "out" / "collections_worklist.csv").exists())
            page = (d / "out" / "dashboard.html").read_text()
            self.assertTrue(page.startswith("<!doctype html>"))
            self.assertNotIn("__PAYLOAD__", page)
            self.assertIn('"customers":[', page)

    def test_run_reports_bad_input(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.csv"
            bad.write_text("foo,bar\n1,2\n")
            self.assertEqual(main(["run", "--ledger", str(bad), "--out", str(Path(d) / "o")]), 2)


if __name__ == "__main__":
    unittest.main()
