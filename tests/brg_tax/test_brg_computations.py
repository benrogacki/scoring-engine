"""Capital allowances, CT schedule and rates, income tax, NIC, DLA, sole trader, VAT and deadlines."""
from datetime import date

from brg_tax.engine import capital_allowances as cam, deadlines, extraction, taxmath, vat
from brg_tax.engine.ct import ct_schedule
from brg_tax.models import Asset, DLAEntry
from brg_tax.money import to_pence
from helpers import client, ctx

P = to_pence


def A(**kw):
    base = {"id": "A", "description": "asset", "date_acquired": date(2025, 6, 1), "cost": 10000}
    base.update(kw)
    return Asset(**base)


# --------------------------------------------------------------- capital allowances
def test_full_expensing_vs_aia_vs_wda_only():
    x = ctx(client())
    a = [A(cost=50000, asset_class="plant", new_unused=True)]
    assert cam.compute(x, a, date(2025, 4, 1), date(2026, 3, 31)).allowances == P(50000)
    s = cam.all_strategies(x, a, date(2025, 4, 1), date(2026, 3, 31))
    assert s["wda_only"] == P(9000)                  # 18% WDA only


def test_used_plant_aia_then_pool_when_limit_exhausted_in_short_period():
    x = ctx(client())
    a = [A(cost=600000, asset_class="plant", new_unused=False)]
    # 6-month period 1 Apr - 30 Sep 2025 (183 days): AIA limit 1,000,000 x 183/365 = 501,369.86
    r = cam.compute(x, a, date(2025, 4, 1), date(2025, 9, 30))
    assert r.aia_limit == P("501369.86")
    # remainder 98,630.14 in the main pool, WDA 98,630.14 x 18% x 183/365 = 8,901.0349 -> 8,901.03
    assert r.allowances == P("501369.86") + P("8901.03")


def test_hybrid_wda_rate_across_1_april_2026():
    x = ctx(client(pools_bf={"main": 100000}))
    r = cam.compute(x, [], date(2025, 10, 1), date(2026, 9, 30))
    # 182 days at 18% + 183 days at 14% over 365: 100,000 x (18 x 182 + 14 x 183) / 36500 = 15,994.52
    assert r.allowances == P("15994.52")


def test_small_pool_and_disposal_balancing_charge():
    x = ctx(client(pools_bf={"main": 900}))
    assert cam.compute(x, [], date(2025, 4, 1), date(2026, 3, 31)).allowances == P(900)
    x2 = ctx(client(pools_bf={"main": 1000}))
    disp = [A(cost=8000, asset_class="van", pool_bf=True, disposal_date=date(2025, 8, 1), disposal_proceeds=3000)]
    r = cam.compute(x2, disp, date(2025, 4, 1), date(2026, 3, 31))
    assert r.charges == P(2000) and r.allowances == 0


def test_full_expensed_disposal_s45u():
    x = ctx(client())
    r = cam.compute(x, [A(cost=20000, asset_class="plant", pool_bf=True, claimed_fe=True, disposal_date=date(2025, 9, 1), disposal_proceeds=7000)],
                    date(2025, 4, 1), date(2026, 3, 31))
    assert r.charges == P(7000)


def test_cars_by_co2_and_zero_emission():
    x = ctx(client())
    r = cam.compute(x, [A(id="c1", cost=30000, asset_class="car", co2_gkm=40, new_unused=True),
                        A(id="c2", cost=20000, asset_class="car", co2_gkm=0, new_unused=True)], date(2025, 4, 1), date(2026, 3, 31))
    assert r.allowances == P(20000) + P(5400)         # 100% FYA on the EV; 18% on the 40g/km car


def test_private_use_single_asset_pool_sole_trader():
    x = ctx(client("sole_trader", package="freeagent"))
    r = cam.compute(x, [A(cost=14000, asset_class="van", new_unused=False, private_use_pct=10)], date(2025, 4, 1), date(2026, 3, 31))
    assert r.allowances == P(12600)


def test_sba_time_apportioned():
    x = ctx(client())
    r = cam.compute(x, [A(cost=100000, asset_class="building", brought_into_use=date(2026, 1, 1))], date(2025, 4, 1), date(2026, 3, 31))
    assert r.allowances == P("739.73")               # 100,000 x 3% x 90/365 = 739.726


def test_aia_shared_with_associate_goes_to_review():
    x = ctx(client(associated_companies=1))
    cam.compute(x, [A(cost=5000, asset_class="plant", new_unused=False)], date(2025, 4, 1), date(2026, 3, 31))
    assert x.review[0].rule_id == "CA-AIA-02"


# --------------------------------------------------------------- corporation tax
def test_ct_rates_small_main_marginal():
    x = ctx(client())
    s = ct_schedule(x, date(2025, 4, 1), date(2026, 3, 31), 0)
    assert taxmath.ct_on_profit(P(40000), P(40000), s)["ct"] == P(7600)
    assert taxmath.ct_on_profit(P(300000), P(300000), s)["ct"] == P(75000)
    # 100,000: 25,000 - (250,000 - 100,000) x 3/200 = 22,750
    assert taxmath.ct_on_profit(P(100000), P(100000), s)["ct"] == P(22750)


def test_associates_divide_limits():
    x = ctx(client())
    s = ct_schedule(x, date(2025, 4, 1), date(2026, 3, 31), 3)
    assert s["slices"][0]["upper"] == P(62500) and s["slices"][0]["lower"] == P(12500)


# --------------------------------------------------------------- income tax and NIC
def ty(label="2025-26"):
    return extraction.ty_model(ctx(client()), label)[0]


def bands(region, label="2025-26"):
    return extraction.region_bands(ctx(client()), region, label)[0]


def test_income_tax_ruk_scotland_and_taper():
    t = ty()
    assert taxmath.income_tax(P(50270), 0, bands("england"), t)["total"] == P(7540)
    # Scotland 2025-26 (seeded bands): 2,827 x 19% + 12,094 x 20% + 16,171 x 21% + 6,608 x 42%
    sco = taxmath.income_tax(P(50270), 0, bands("scotland"), t)["total"]
    assert sco == P("537.13") + P("2418.80") + P("3395.91") + P("2775.36")
    # PA taper: income 110,000 -> PA 12,570 - 5,000 = 7,570
    assert taxmath.income_tax(P(110000), 0, bands("england"), t)["pa"] == P(7570)
    assert taxmath.personal_allowance(P(125140), t) == 0


def test_dividend_tax_uses_allowance_and_bands():
    t = ty()
    # salary 12,570 + dividends 40,000: allowance 500 at 0%, then basic band left 37,700 - 500 = 37,200 at 8.75%,
    # remaining 2,300 at 33.75%
    r = taxmath.income_tax(P(12570), P(40000), bands("england"), t)
    assert r["tax_div"] == P("3255.00") + P("776.25")
    t27 = ty("2026-27")
    assert t27["div_bp"][:2] == [1075, 3575]


def test_class1_director_and_class4_class2():
    t = ty()
    assert taxmath.class1(P(12570), t) == {"ee": 0, "er": P("1135.50")}
    assert taxmath.class1(P(60000), t)["ee"] == P(3016) + P("194.60")
    t24 = ty("2023-24")
    assert t24["ee_main_bp"] == 1150
    assert taxmath.class2(P(20000), t24) == P("3.45") * 52
    assert taxmath.class2(P(20000), t) == 0
    assert taxmath.class4(P(60000), t) == P(2262) + P("194.60")


def test_employment_allowance_single_director_excluded():
    x = ctx(client())
    m = {"ty": ty("2026-27"), "profit_before_directors": P(100000), "exempt_distributions": 0,
         "ct_schedule": {"days": 365, "slices": [{k: v for k, v in s.items() if k in ("fy", "days", "main_bp", "small_bp", "mr_num", "mr_den", "upper", "lower")}
                                                  for s in ct_schedule(x, date(2026, 4, 1), date(2027, 3, 31), 0, planning=True)["slices"]]},
         "opening_reserves": 0, "other_employees_above_st": 0, "other_employer_nic": 0, "retain_pct": 0, "dla_overdrawn": {},
         "people": [{"id": "d1", "name": "D", "share_bp": 10000, "director": True, "other_income": 0, "ns_bands": bands("england", "2026-27"), "waived": False}],
         "default": {"pensions": {"d1": 0}, "clear_dla": False}}
    one = taxmath.scenario(m, {"salaries": {"d1": P(20000)}, "pensions": {}, "dividend_total": 0})
    assert not one["ea_eligible"] and one["er_nic_net"] == P(2250)
    m2 = dict(m, people=m["people"] + [dict(m["people"][0], id="d2")])
    two = taxmath.scenario(m2, {"salaries": {"d1": P(20000), "d2": P(20000)}, "pensions": {}, "dividend_total": 0})
    assert two["ea_eligible"] and two["er_nic_net"] == 0
    big = taxmath.scenario(m, {"salaries": {"d1": 0}, "pensions": {}, "dividend_total": P(500000)})
    assert big["hard_stop"]


def test_dla_s464c_dividend_repayment_is_not_matched():
    c = client(people=[{"id": "d1", "name": "D", "shares": 1}])
    from brg_tax.models import ClientData
    entries = [DLAEntry(date=date(2026, 1, 1), person_id="d1", amount=P(8000)),
               DLAEntry(date=date(2026, 4, 10), person_id="d1", amount=-P(8000), method="dividend"),
               DLAEntry(date=date(2026, 4, 20), person_id="d1", amount=P(8000))]
    x = ctx(c)
    out = extraction.dla_monitor(x, ClientData(client=c, dla=entries))
    p = out["people"][0]
    assert p["s464c_matched"] == 0 and p["s455"] == 0
    assert not any(r.rule_id.startswith("AA-464C") for r in x.review)


# --------------------------------------------------------------- VAT and deadlines
def test_vat_historic_breach_detected():
    from brg_tax.models import ClientData, Transaction
    c = client("sole_trader", package="freeagent")
    from brg_tax.dates import add_months
    # 9,000 a month from October 2025: the 12-month total first exceeds 90,000 at the end of August 2026 (99,000)
    tx = [Transaction(id=f"s{i}", date=add_months(date(2025, 10, 15), i, month_end_rule=False), code="1", net=P(9000),
                      category="sales", side="income") for i in range(12)]
    x = ctx(c)
    out = vat.monitor(x, ClientData(client=c, transactions=tx), [])
    t = next(t for t in out["tests"] if t["rule"] == "VAT-REG-01")
    assert t["result"] == "must register" and t["month_end"] == "2026-08-31" and t["effective"] == "2026-10-01"
    assert any(f["rule"] == "VAT-REG-01" and f["severity"] == "critical" for f in x.flags)


def test_deadlines_month_end_rule():
    c = client(periods=[{"start": "2025-07-01", "end": "2026-06-30"}], confirmation_statement_date="2026-09-12")
    x = ctx(c)
    ev = {e["rule"]: e["date"] for e in deadlines.generate(x, {}) if e["for"] == "period ended 2026-06-30"}
    assert ev["DL-CTPAY-01"] == "2027-04-01"           # 30 June + 9 months (31 March) + 1 day
    assert ev["DL-CHACC-01"] == "2027-03-31"
    assert ev["DL-CT600-01"] == "2027-06-30"
