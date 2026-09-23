import csv
import io
import json
import tempfile
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest import mock

from scoring_engine import engine
from scoring_engine.cli import main
from scoring_engine.config import load_config
from scoring_engine.loader import merge_customers, rows_to_customers, rows_to_invoices
from scoring_engine.sources import databricks as dbx
from scoring_engine.sources import netsuite as ns

AS_OF = date(2026, 9, 30)

# Rows shaped like SuiteQL output from queries/netsuite_invoices.sql (lower-case keys, strings).
NS_INVOICES = [
    {"invoice_id": "101", "invoice_number": "INV101", "customer_id": "7", "invoice_date": "2026-05-01",
     "due_date": "2026-05-31", "amount": "1200.5", "amount_remaining": "0", "paid_date": "2026-06-10", "disputed": "F"},
    {"invoice_id": "102", "invoice_number": "INV102", "customer_id": "7", "invoice_date": "2026-08-01",
     "due_date": "2026-08-31", "amount": "800", "amount_remaining": "300", "paid_date": "2026-09-05", "disputed": "F"},
    {"invoice_id": "103", "invoice_number": "INV103", "customer_id": "9", "invoice_date": "2026-04-01",
     "due_date": "2026-05-01", "amount": "5000", "amount_remaining": "5000", "paid_date": None, "disputed": "T"},
]
NS_CUSTOMERS = [
    {"customer_id": "7", "customer_name": "Apex Ltd", "credit_limit": "5000", "payment_terms_days": "30", "industry": "Retail"},
    {"customer_id": "9", "customer_name": "Birch plc", "credit_limit": None, "payment_terms_days": None, "industry": None},
]


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Stands in for urllib.request.urlopen and records requests."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        return FakeResponse(json.dumps(self.pages.pop(0)).encode())


def ns_client(opener):
    return ns.NetSuiteClient("1234567_SB1", "ck", "cs", "tk", "ts", opener=opener)


class OAuthTests(unittest.TestCase):
    def test_signature_matches_published_vector(self):
        # Worked example from Twitter's OAuth 1.0a signing documentation.
        header = ns.oauth1_header(
            "POST", "https://api.twitter.com/1.1/statuses/update.json?include_entities=true",
            "xvz1evFS4wEEPTGEFPHBog", "kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw",
            "370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb", "LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE",
            signature_method="HMAC-SHA1", nonce="kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg",
            timestamp="1318622958", body_params={"status": "Hello Ladies + Gentlemen, a signed OAuth request!"},
        )
        self.assertIn('oauth_signature="hCtSmYh%2BiHYCEqBWrE7C7hYmtUk%3D"', header)


class NetSuiteTests(unittest.TestCase):
    def test_pagination_headers_and_url(self):
        opener = FakeOpener([
            {"items": [{"id": "1", "links": []}], "hasMore": True},
            {"items": [{"id": "2", "links": []}], "hasMore": False},
        ])
        rows = list(ns_client(opener).query("SELECT id FROM customer"))
        self.assertEqual(rows, [{"id": "1"}, {"id": "2"}])
        first, second = opener.requests
        self.assertTrue(first.full_url.startswith("https://1234567-sb1.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql"))
        self.assertIn("offset=0", first.full_url)
        self.assertIn("offset=1000", second.full_url)
        auth = first.get_header("Authorization")
        self.assertIn('realm="1234567_SB1"', auth)
        self.assertIn('oauth_signature_method="HMAC-SHA256"', auth)
        self.assertEqual(first.get_header("Prefer"), "transient")
        self.assertEqual(json.loads(first.data), {"q": "SELECT id FROM customer"})

    def test_default_query_is_clean_suiteql(self):
        sql = ns.load_query(None, "netsuite_invoices.sql", lookback_months=15)
        self.assertNotIn("--", sql)
        self.assertNotIn("{lookback_months}", sql)
        self.assertIn("ADD_MONTHS(TRUNC(SYSDATE), -15)", sql)
        self.assertFalse(sql.endswith(";"))

    def test_missing_credentials(self):
        with self.assertRaisesRegex(ns.NetSuiteError, "NETSUITE_TOKEN_SECRET"):
            ns.NetSuiteClient.from_env({"NETSUITE_ACCOUNT_ID": "1", "NETSUITE_CONSUMER_KEY": "a",
                                        "NETSUITE_CONSUMER_SECRET": "b", "NETSUITE_TOKEN_ID": "c"})

    def test_netsuite_rows_score_end_to_end(self):
        invoices = rows_to_invoices(NS_INVOICES, "netsuite")
        by_id = {i.invoice_id: i for i in invoices}
        self.assertTrue(by_id["101"].is_settled)
        self.assertEqual(by_id["102"].outstanding, 300)  # part-paid: stays open
        self.assertTrue(by_id["103"].disputed)
        customers = merge_customers(invoices, rows_to_customers(NS_CUSTOMERS, "netsuite"))
        self.assertEqual(customers["9"].payment_terms_days, 30)
        result = engine.run(invoices, customers, AS_OF, load_config())
        grades = {s.customer.customer_id: s.grade for s in result.scores}
        self.assertEqual(grades["9"], "E")  # 5,000 unpaid 150 days, disputed


class LoaderNativeTypeTests(unittest.TestCase):
    def test_accepts_database_types(self):
        (inv,) = rows_to_invoices([{
            "invoice_id": 1, "customer_id": 42, "invoice_date": date(2026, 1, 1),
            "due_date": datetime(2026, 1, 31, 0, 0), "amount": Decimal("99.90"),
            "amount_paid": Decimal("99.90"), "paid_date": date(2026, 2, 3), "disputed": False,
        }])
        self.assertEqual(inv.customer_id, "42")
        self.assertEqual(inv.due_date, date(2026, 1, 31))
        self.assertEqual(inv.days_late_paid(), 3)
        self.assertFalse(inv.disputed)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.statements.append((sql, params))
        result = self.conn.results.pop(0) if self.conn.results else ([], [])
        cols, self._rows = result
        self.description = [(c,) for c in cols]

    def executemany(self, sql, seq):
        self.conn.statements.append((sql, list(seq)))

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self, results=()):
        self.results = list(results)
        self.statements = []

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        pass


def as_result(rows):
    cols = list(rows[0].keys())
    return cols, [tuple(r[c] for c in cols) for r in rows]


class DatabricksTests(unittest.TestCase):
    def test_fetch_substitutes_tables(self):
        conn = FakeConn([as_result(NS_INVOICES), as_result(NS_CUSTOMERS)])
        data = dbx.fetch(conn, "main.finance.ar_invoices", "main.finance.customers", lookback_months=12)
        self.assertEqual(len(data["invoices"]), 3)
        self.assertEqual(data["customers"][0]["customer_name"], "Apex Ltd")
        inv_sql = conn.statements[0][0]
        self.assertIn("FROM main.finance.ar_invoices", inv_sql)
        self.assertIn("-12)", inv_sql)

    def test_rejects_unsafe_table_names(self):
        with self.assertRaises(dbx.DatabricksError):
            dbx.fetch(FakeConn(), "x; DROP TABLE y")

    def test_spark_path(self):
        class Row(dict):
            def asDict(self):
                return dict(self)

        class Spark:
            def __init__(self):
                self.queries = []

            def sql(self, q):
                self.queries.append(q)
                rows = NS_INVOICES if "invoice" in q else NS_CUSTOMERS
                return mock.Mock(collect=lambda: [Row(r) for r in rows])

        spark = Spark()
        data = dbx.fetch(None, "cat.sch.inv", "cat.sch.cust", spark=spark)
        self.assertEqual(len(data["invoices"]), 3)
        self.assertEqual(len(spark.queries), 2)

    def test_write_table_is_idempotent_per_date(self):
        conn = FakeConn()
        rows = [{"customer_id": "7", "grade": "A", "composite_score": "91.5", "collection_rank": ""}]
        dbx.write_table(conn, "main.finance.credit_risk_scorecard", rows, AS_OF)
        (create, _), (delete, dparams), (insert, values) = conn.statements
        self.assertIn("CREATE TABLE IF NOT EXISTS main.finance.credit_risk_scorecard", create)
        self.assertIn("`composite_score` DOUBLE", create)
        self.assertIn("`customer_id` STRING", create)  # IDs keep leading zeros
        self.assertIn("`grade` STRING", create)
        self.assertEqual(dparams, [AS_OF])
        self.assertEqual(values, [(AS_OF, "7", "A", 91.5, None)])


class CliSourceTests(unittest.TestCase):
    def test_run_and_extract_from_netsuite(self):
        def fake_fetch(client, lookback, iq, cq):
            return {"invoices": [dict(r) for r in NS_INVOICES], "customers": [dict(r) for r in NS_CUSTOMERS]}

        fake_client = mock.Mock(account_id="1234567")
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(ns.NetSuiteClient, "from_env", return_value=fake_client), \
                mock.patch.object(ns, "fetch", side_effect=fake_fetch):
            d = Path(d)
            rc = main(["run", "--source", "netsuite", "--as-of", "2026-09-30", "--out", str(d / "out")])
            self.assertEqual(rc, 0)
            with open(d / "out" / "scorecard.csv") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual({r["customer_name"] for r in rows}, {"Apex Ltd", "Birch plc"})
            self.assertIn("NetSuite 1234567", (d / "out" / "dashboard.html").read_text())

            rc = main(["extract", "--source", "netsuite", "--out", str(d / "data")])
            self.assertEqual(rc, 0)
            # The extract re-runs offline through the CSV path.
            rc = main(["run", "--ledger", str(d / "data" / "ledger.csv"), "--customers", str(d / "data" / "customers.csv"),
                       "--as-of", "2026-09-30", "--out", str(d / "out2")])
            self.assertEqual(rc, 0)

    def test_missing_credentials_is_a_clean_error(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(main(["run", "--source", "netsuite", "--out", "unused"]), 2)


if __name__ == "__main__":
    unittest.main()
