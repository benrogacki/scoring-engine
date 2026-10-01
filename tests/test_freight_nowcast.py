import json
import math
import random
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from freight_nowcast import engine
from freight_nowcast.catalog import CatalogError, check_catalog, load_catalog
from freight_nowcast.cli import main
from freight_nowcast.composite import phase
from freight_nowcast.feed import SCHEMA, build_feed
from freight_nowcast.series import Series, add_months, rolling_zscore, transform
from freight_nowcast.sources import SourceError, parse_number, parse_period, read_csv_series
from freight_nowcast.sources import ais, genesis, sdmx
from freight_nowcast.stats import ols
from freight_nowcast.turning import confirmed_turning_points, provisional_turn
from freight_nowcast.validation import validate_pair

AS_OF = date(2026, 9, 30)


def months(n, start=(2010, 1)):
    out, m = [], start
    for _ in range(n):
        out.append(m)
        m = add_months(m, 1)
    return out


class ParsingTests(unittest.TestCase):
    def test_periods(self):
        self.assertEqual(parse_period("2026-09-14"), date(2026, 9, 14))
        self.assertEqual(parse_period("2026-09"), date(2026, 9, 1))
        self.assertEqual(parse_period("2026-M09"), date(2026, 9, 1))
        self.assertEqual(parse_period("2026M09"), date(2026, 9, 1))
        self.assertEqual(parse_period("2026-Q3"), date(2026, 7, 1))
        self.assertEqual(parse_period("2026-W38"), date(2026, 9, 14))
        self.assertEqual(parse_period("14.09.2026"), date(2026, 9, 14))
        self.assertEqual(parse_period("Sep 14, 2026"), date(2026, 9, 14))
        self.assertEqual(parse_period("09/14/2026", "%m/%d/%Y"), date(2026, 9, 14))
        with self.assertRaises(SourceError):
            parse_period("sometime")

    def test_numbers(self):
        self.assertEqual(parse_number("1,234.5"), 1234.5)
        self.assertEqual(parse_number("1.234,5", ","), 1234.5)
        self.assertEqual(parse_number("103.4p"), 103.4)
        self.assertIsNone(parse_number("..."))
        self.assertIsNone(parse_number("-"))

    def test_csv_series_guesses_columns(self):
        s = read_csv_series("bdi", '"Date","Price","Vol."\n"Sep 14, 2026","1,523.00",""\n"Sep 15, 2026","1,540.00",""\n', "D")
        self.assertEqual(s.observations, [(date(2026, 9, 14), 1523.0), (date(2026, 9, 15), 1540.0)])


class SeriesTests(unittest.TestCase):
    def test_daily_to_monthly_marks_month_to_date(self):
        obs = [(date(2026, 8, 1) + timedelta(days=i), 100.0 + i) for i in range(31 + 10)]
        vals, cov = Series("x", obs, "D").to_monthly()
        self.assertAlmostEqual(vals[(2026, 8)], 115.0)
        self.assertEqual(cov[(2026, 8)], 1.0)
        self.assertAlmostEqual(cov[(2026, 9)], 10 / 30, places=3)

    def test_transforms(self):
        lvl = {m: 100 * 1.01 ** i for i, m in enumerate(months(30))}
        self.assertAlmostEqual(transform(lvl, "mom")[(2010, 6)], 1.0)
        self.assertAlmostEqual(transform(lvl, "yoy")[(2011, 6)], (1.01 ** 12 - 1) * 100)
        self.assertAlmostEqual(transform(lvl, "3m3m")[(2011, 6)], (1.01 ** 12 - 1) * 100)

    def test_zscore_has_no_lookahead(self):
        rng = random.Random(1)
        x = {m: rng.gauss(0, 1) for m in months(80)}
        z_short = rolling_zscore({m: v for m, v in x.items() if m <= (2014, 12)})
        z_full = rolling_zscore(x)
        for m, v in z_short.items():
            self.assertAlmostEqual(v, z_full[m])


class StatsTests(unittest.TestCase):
    def test_ols_recovers_coefficients(self):
        rng = random.Random(3)
        xs = [rng.gauss(0, 1) for _ in range(300)]
        ys = [0.5 + 2.0 * x + rng.gauss(0, 0.5) for x in xs]
        fit = ols(ys, [[x] for x in xs])
        self.assertAlmostEqual(fit.coef[1], 2.0, delta=0.1)
        self.assertAlmostEqual(fit.coef[0], 0.5, delta=0.1)
        self.assertGreater(fit.t[1], 20)
        self.assertGreater(fit.r2, 0.9)


def linked(n=180, beta=1.0, noise=0.6, seed=5):
    rng = random.Random(seed)
    c, x, y = 0.0, {}, {}
    lx = ly = 100.0
    for m in months(n):
        c = 0.8 * c + rng.gauss(0, 1)
        lx *= 1 + (0.9 * c + rng.gauss(0, 0.3)) / 100
        ly *= 1 + (beta * c + rng.gauss(0, noise)) / 100
        x[m], y[m] = lx, ly
    return x, y


class ValidationTests(unittest.TestCase):
    def test_linked_pair_is_evidenced(self):
        x, y = linked()
        r = validate_pair(x, y, "mom")
        self.assertEqual(r.verdict, "evidenced", r.notes)
        self.assertEqual(r.best_lead, 0)
        self.assertLess(r.rmse_ratio, 1)

    def test_unrelated_pair_is_not_evidenced(self):
        x, _ = linked(seed=1)
        _, y = linked(seed=2)
        self.assertNotEqual(validate_pair(x, y, "mom").verdict, "evidenced")

    def test_short_overlap(self):
        x, y = linked(n=20)
        self.assertEqual(validate_pair(x, y).verdict, "insufficient data")


class TurningPointTests(unittest.TestCase):
    def test_sine_cycle(self):
        ms = months(96)
        x = {m: math.sin(2 * math.pi * i / 36) for i, m in enumerate(ms)}
        tps = confirmed_turning_points(x)
        kinds = [t.kind for t in tps]
        self.assertTrue(all(a != b for a, b in zip(kinds, kinds[1:])))
        peaks = [ms.index(t.month) for t in tps if t.kind == "peak"]
        self.assertEqual(peaks, [9, 45, 81])

    def test_provisional_peak_at_edge(self):
        ms = months(30)
        x = {m: (i if i <= 25 else 25 - 2 * (i - 25)) / 10 for i, m in enumerate(ms)}
        t = provisional_turn(x, None)
        self.assertIsNotNone(t)
        self.assertEqual((t.kind, t.month), ("peak", ms[25]))

    def test_phase_clock(self):
        x = {(2026, 1): -1.0, (2026, 4): -0.5, (2026, 7): 0.5, (2026, 10): 0.2}
        self.assertEqual(phase(x, (2026, 4)), "Recovery")
        self.assertEqual(phase(x, (2026, 7)), "Expansion")
        self.assertEqual(phase(x, (2026, 10)), "Slowdown")


FFCSV = """statistics_code;statistics_label;time_code;time_label;time;1_variable_code;1_variable_label;1_variable_attribute_code;1_variable_attribute_label;2_variable_code;2_variable_label;2_variable_attribute_code;2_variable_attribute_label;value;value_unit;value_variable_code;value_variable_label
42191;Toll;JAHR;Year;2026;DINSG;Germany;DG;Germany;MONAT;Month;MONAT07;July;101.2;2015=100;LKW001;Index
42191;Toll;JAHR;Year;2026;DINSG;Germany;DG;Germany;MONAT;Month;MONAT08;August;99.8;2015=100;LKW001;Index
"""


class GenesisTests(unittest.TestCase):
    def test_parse_long_ffcsv(self):
        text = FFCSV.replace("DINSG;Germany;DG;Germany", "WERTE4;Adjustment;X13JDKSB;Adjusted")
        text += text.splitlines()[1].replace("X13JDKSB", "ORIGINAL").replace("101.2", "95.0") + "\n"
        obs = genesis.parse_ffcsv(text, {"WERTE4": "X13JDKSB"})
        self.assertEqual(obs, [(date(2026, 7, 1), 101.2), (date(2026, 8, 1), 99.8)])
        with self.assertRaises(SourceError):  # two lines for July without a filter
            genesis.parse_ffcsv(text)

    def test_parse_german_headers_and_decimal_comma(self):
        text = (FFCSV.replace("statistics", "Statistik").replace("variable_attribute", "Auspraegung")
                .replace("variable", "Merkmal").replace(";time", ";Zeit").replace("value", "Wert")
                .replace("101.2", "101,2"))
        self.assertEqual(genesis.parse_ffcsv(text)[0], (date(2026, 7, 1), 101.2))

    def test_parse_wide_value_columns(self):
        text = ("time;1_variable_code;1_variable_attribute_code;LKW001__Index__2015=100;LKW002__Change__%\n"
                "2026;MONAT;MONAT07;101,2;0,5\n")
        self.assertEqual(genesis.parse_ffcsv(text, value_variable="LKW001"), [(date(2026, 7, 1), 101.2)])
        with self.assertRaises(SourceError):
            genesis.parse_ffcsv(text)

    def test_inspect(self):
        info = genesis.inspect_ffcsv(FFCSV)
        self.assertIn("DINSG", info["variables"])
        self.assertNotIn("MONAT", info["variables"])

    def test_client_sends_credentials_in_headers(self):
        seen = {}

        def transport(url, headers, form):
            seen.update(url=url, headers=headers, form=form)
            return FFCSV.encode()

        client = genesis.GenesisClient("TOKEN123", "", "https://example/rest/2020", transport)
        s = genesis.fetch("toll", "M", "42191-0001", client=client, startyear=2020)
        self.assertEqual(seen["url"], "https://example/rest/2020/data/tablefile")
        self.assertEqual(seen["headers"]["username"], "TOKEN123")
        self.assertNotIn("username", seen["form"])
        self.assertEqual(seen["form"]["format"], "ffcsv")
        self.assertEqual(len(s.observations), 2)

    def test_json_status_is_an_error(self):
        client = genesis.GenesisClient("u", "p", transport=lambda *a: b'{"Status": {"Content": "Login failed"}}')
        with self.assertRaisesRegex(SourceError, "Login failed"):
            client.tablefile("42191-0001")


SDMX_CSV = """DATAFLOW,freq,indic_bt,nace_r2,s_adj,unit,geo,TIME_PERIOD,OBS_VALUE,OBS_FLAG
ESTAT:STS_INPR_M(1.0),M,PRD,C,SCA,I21,DE,2026-06,98.1,
ESTAT:STS_INPR_M(1.0),M,PRD,C,SCA,I21,DE,2026-07,97.4,p
ESTAT:STS_INPR_M(1.0),M,PRD,C,SCA,I21,FR,2026-07,101.0,
"""


class SdmxTests(unittest.TestCase):
    def test_build_url(self):
        url = sdmx.build_url("eurostat", "sts_inpr_m", "M.PRD.C.SCA.I21.DE", start="2008-01")
        self.assertTrue(url.startswith("https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/sts_inpr_m/M.PRD.C.SCA.I21.DE?"))
        self.assertIn("startPeriod=2008-01", url)

    def test_multiple_series_need_pinning(self):
        with self.assertRaisesRegex(SourceError, "geo"):
            sdmx.parse_sdmx_csv(SDMX_CSV)
        obs = sdmx.parse_sdmx_csv(SDMX_CSV, {"geo": "DE"})
        self.assertEqual(obs, [(date(2026, 6, 1), 98.1), (date(2026, 7, 1), 97.4)])

    def test_fetch_with_getter(self):
        s = sdmx.fetch("ip", "M", url="https://x/data", filters={"geo": "FR"}, getter=lambda u: SDMX_CSV.encode())
        self.assertEqual(s.observations, [(date(2026, 7, 1), 101.0)])


class AisTests(unittest.TestCase):
    def test_counts_vessels_per_port(self):
        c = ais.PortCounter({"Hamburg": ((53.50, 9.80), (53.56, 10.05)), "Rotterdam": ((51.88, 3.95), (51.99, 4.55))})
        sub = c.subscription("KEY")
        self.assertEqual(sub["BoundingBoxes"][0], [[53.50, 9.80], [53.56, 10.05]])

        def msg(mmsi, lat, lon, sog, nav=0):
            return {"MessageType": "PositionReport", "MetaData": {"MMSI": mmsi},
                    "Message": {"PositionReport": {"UserID": mmsi, "Latitude": lat, "Longitude": lon,
                                                   "Sog": sog, "NavigationalStatus": nav}}}

        self.assertEqual(c.ingest(msg(1, 53.53, 9.9, 0.1)), "Hamburg")
        c.ingest(msg(1, 53.53, 9.9, 0.2))  # same vessel twice
        c.ingest(msg(2, 53.54, 9.95, 12.0))
        c.ingest(msg(3, 53.52, 9.85, 3.0, nav=5))  # moored
        self.assertIsNone(c.ingest(msg(4, 0.0, 0.0, 0.0)))
        self.assertIsNone(c.ingest({"MessageType": "ShipStaticData", "Message": {}}))
        rows = {r["port"]: r for r in c.summary(AS_OF, 5)}
        self.assertEqual((rows["Hamburg"]["vessels"], rows["Hamburg"]["stationary"]), (3, 2))
        self.assertEqual(rows["Rotterdam"]["vessels"], 0)


class CatalogTests(unittest.TestCase):
    def test_default_catalog_is_valid(self):
        cfg = load_catalog()
        self.assertIn("de_toll_mileage", [s["id"] for s in cfg["series"]])

    def test_bad_catalog(self):
        with self.assertRaises(CatalogError):
            check_catalog({"geographies": {}, "series": [{"id": "a", "role": "indicator", "source": "csv",
                                                           "geography": "XX", "transform": "weird"}]})


class PipelineTests(unittest.TestCase):
    def test_daily_toll_extends_monthly_at_ragged_edge(self):
        cfg = load_catalog()
        ms = months(60, (2021, 9))
        monthly = Series("de_toll_mileage", [(date(*m, 1), 100.0 + i * 0.1) for i, m in enumerate(ms)], "M")
        last = ms[-1]
        d, daily = date(2025, 1, 1), []
        while d <= date(2026, 9, 10):
            m = (d.year, d.month)
            base = monthly.observations[ms.index(m)][1] if m in ms else 120.0
            daily.append((d, base / 1.05))
            d += timedelta(days=1)
        warnings = []
        out = engine.splice_extensions({"de_toll_mileage": monthly, "de_toll_mileage_daily": Series("de_toll_mileage_daily", daily, "D")},
                                       {s["id"]: s for s in cfg["series"]}, AS_OF, warnings)
        vals, cov = out["de_toll_mileage"].to_monthly(AS_OF)
        self.assertEqual(max(vals), (2026, 9))
        self.assertGreater(last, (2026, 7))
        self.assertAlmostEqual(vals[(2026, 9)], 120.0, places=6)  # rebased by the 1.05 ratio
        self.assertAlmostEqual(cov[(2026, 9)], 10 / 30, places=3)
        self.assertEqual(warnings, [])

    def test_demo_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rc = main(["demo", "--as-of", AS_OF.isoformat(), "--cache", str(tmp / "cache"), "--out", str(tmp / "out")])
            self.assertEqual(rc, 0)
            for name in ("composite.csv", "indicator_panel.csv", "turning_points.csv", "validation.json",
                         "capstone_feed.json", "nowcast_summary.md", "dashboard.html"):
                self.assertTrue((tmp / "out" / name).exists(), name)
            feed = json.loads((tmp / "out" / "capstone_feed.json").read_text())
            self.assertEqual(feed["schema"], SCHEMA)
            self.assertIn(feed["tier1"]["phase"], ("Recovery", "Expansion", "Slowdown", "Contraction"))
            self.assertEqual(set(feed["tier1"]["by_geography"]), {"DE", "EA", "WORLD"})
            self.assertTrue(feed["tier1"]["by_geography"]["DE"]["provisional"])  # month-to-date daily toll
            verdicts = {f"{v['indicator']}->{v['target']}": v["verdict"] for v in feed["validation"]}
            self.assertEqual(verdicts["de_toll_mileage->de_manufacturing_production"], "evidenced")
            self.assertEqual(verdicts["baltic_dry->world_trade_volume"], "not evidenced")
            self.assertTrue(any("SYNTHETIC" in w for w in feed["warnings"]))
            html = (tmp / "out" / "dashboard.html").read_text()
            self.assertNotIn("/*__DATA__*/null", html)

    def test_run_without_data_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["run", "--cache", tmp, "--out", str(Path(tmp) / "out")]), 2)


if __name__ == "__main__":
    unittest.main()
