"""Golden tests: each synthetic client hand-calculated, asserted to the penny.

All rates and thresholds below are the seeded (unverified) parameter values for the year shown. If
`brg-tax params-update` or a hand edit changes a value, these expectations must be re-worked by hand,
not copied from the engine.

Rounding convention (rule CT-SHORT-01 / brg_tax/money.py): amounts in pence, half-up to the penny at
each tax step; CT limits reduced for associates and short periods, then split by financial year by
days with the remainder in the last slice.
"""
from brg_tax.money import to_pence


def P(x):
    return to_pence(x)


def line(c, key):
    return next(l for l in c["computation"]["lines"] if l["key"] == key)


# ---------------------------------------------------------------------------------------------
# Client 1 - Asha Patel Consulting, sole trader, England, year to 31 March 2026 = 2025-26.
#
#   Sales 12 x 6,500                                              78,000.00
#   Expenses: software 1,200 + insurance 600 + accountancy 900 + mileage 900 + entertaining 350
#             + phone 480 + training 500 + use of home 312 + depreciation 500   =  5,742.00
#   Net profit per accounts                                        72,258.00
#   Add: depreciation (EXP-DEP-01)                                    500.00
#   Add: client entertaining (EXP-ENT-01)                             350.00
#   Add: phone private use 20% x 480 (EXP-PRIV-01)                     96.00
#   Mileage 2,000 miles x 45p = 900.00 = amount claimed -> no adjustment (EXP-MILE-01)
#   Use of home 101+ hours: £26 x 12 = 312.00 = amount booked -> no adjustment (EXP-HOME-01)
#   Less: AIA on laptop (CA-AIA-01)                                (1,500.00)
#   Taxable trading profit                                         71,704.00
#   Income tax: 71,704 - PA 12,570 = 59,134; 37,700 x 20% = 7,540.00; 21,434 x 40% = 8,573.60 -> 16,113.60
#   Class 4: (50,270 - 12,570) x 6% = 2,262.00; (71,704 - 50,270) x 2% = 428.68            ->  2,690.68
#   Class 2 2025-26: none payable (profits above the small profits threshold are credited)
#   Total 18,804.28; POAs paid 15,000 -> balancing payment 3,804.28
#   POAs for 2026-27: (16,113.60 + 2,690.68) / 2 = 9,402.14 each
#   VAT: rolling 12 months to 30 Sep 2026 = 6 x 6,500 + 6 x 7,500 = 84,000.00 (93% of 90,000)
# ---------------------------------------------------------------------------------------------
def test_client1_sole_trader(by_id):
    c = by_id["c01-asha-patel"]
    comp = c["computation"]
    assert comp["tax_year"] == "2025-26"
    assert comp["accounting_profit"] == P("72258.00")
    assert line(c, "addback_EXP-DEP-01")["amount"] == P("500.00")
    assert line(c, "addback_EXP-ENT-01")["amount"] == P("350.00")
    assert line(c, "addback_EXP-PRIV-01")["amount"] == P("96.00")
    assert comp["taxable_profit"] == P("71704.00")
    assert comp["income_tax"] == P("16113.60")
    assert comp["class4"] == P("2690.68")
    assert comp["class2"] == 0
    assert comp["liability"] == P("18804.28")
    assert comp["balancing"] == P("3804.28")
    assert comp["poa_next"] == P("9402.14")
    reg = next(t for t in c["vat"]["tests"] if t["rule"] == "VAT-REG-01")
    assert reg["turnover"] == P("84000.00") and reg["result"] == "below threshold" and reg["pct"] == 93
    assert c["sa"]["mtd"]["mandated_from"] == "2027-28" and not c["sa"]["mtd"]["mandated_now"]
    assert c["open_review"] == 0


# ---------------------------------------------------------------------------------------------
# Client 2 - Brightside Design Ltd, single director, year to 31 March 2026 (FY2025, 365 days).
#
#   Sales 12 x 6,000                                               72,000.00
#   Costs: salary 12,570 + employer NIC 1,135.50 + software 2,400 + rent 6,000 + accountancy 1,800
#          + staff Christmas meal 140 + client dinner 600 + branded gifts 240 + parking penalty 60
#          + depreciation 800 + bank charges 120                   = 25,865.50
#   (Employer NIC: (12,570 - 5,000) x 15% = 1,135.50; no Employment Allowance - sole director)
#   Profit per accounts                                             46,134.50
#   Add: depreciation 800, client entertaining 600, penalty 60      1,460.00
#   Less: full expensing on new laptop (CA-FE-01)                  (2,000.00)
#   Taxable total profits                                           45,594.50
#   Below the lower limit 50,000 -> small profits rate 19%: 45,594.50 x 19% = 8,662.955 -> 8,662.96
#
#   DLA: 0 -> +4,000 (30/6/25) -> +4,000 (30/9/25) -> +4,000 (15/1/26) -> -3,000 (28/2/26)
#        year-end balance 9,000.00. Repaid 6,000 on 20/4/26 and 6,000 redrawn 10/5/26 (20 days):
#        s464C(1) matches the repayment, so it does not reduce the charge.
#   s455: 9,000.00 x 33.75% = 3,037.50, due 1 January 2027.
#   Beneficial loan 2025-26 (peak 12,000 > 10,000):
#     averaging: first balance 4,000 (30/6/25), closing 9,000 (5/4/26); complete tax months
#       6 July 2025 to 5 April 2026 = 9; (4,000 + 9,000)/2 x 3.75% x 9/12 = 182.8125 -> 182.81
#     alternative: 4,000 x 92 + 8,000 x 107 + 12,000 x 44 + 9,000 x 37 = 2,085,000 pound-days
#       x 3.75% / 365 = 214.2123 -> 214.21
#     Class 1A: 182.81 x 15% = 27.4215 -> 27.42
# ---------------------------------------------------------------------------------------------
def test_client2_small_company_and_dla(by_id):
    c = by_id["c02-brightside"]
    comp = c["computation"]
    assert comp["accounting_profit"] == P("46134.50")
    assert line(c, "addback_EXP-DEP-01")["amount"] == P("800.00")
    assert line(c, "addback_EXP-ENT-01")["amount"] == P("600.00")
    assert line(c, "addback_EXP-FINE-01")["amount"] == P("60.00")
    assert c["ca"]["allowances"] == P("2000.00")
    assert comp["ttp"] == P("45594.50")
    assert [s["rate"] for s in comp["slices"]] == ["small"]
    assert comp["liability"] == P("8662.96")
    d = c["dla"]["people"][0]
    assert d["year_end_balance"] == P("9000.00")
    assert d["s464c_matched"] == P("6000.00")
    assert d["s455_base"] == P("9000.00")
    assert d["s455"] == P("3037.50")
    assert c["dla"]["due_date"] == "2027-01-01"
    assert d["bik"]["months"] == 9
    assert d["bik"]["averaging"] == P("182.81")
    assert d["bik"]["alternative"] == P("214.21")
    assert d["bik"]["class1a"] == P("27.42")
    assert any(r["rule_id"] == "AA-464C-01" and r["kind"] == "anti_avoidance" for r in c["review"])
    assert not c["extraction"]["default"]["result"]["ea_eligible"]


# ---------------------------------------------------------------------------------------------
# Client 3 - Northgate Engineering Ltd: 9-month period 1 Oct 2025 - 30 Jun 2026 (273 days),
# one associated company, straddling 1 April 2026 (FY2025: 182 days, FY2026: 91 days).
#
#   Sales 9 x 20,000                                              180,000.00
#   Costs: materials 63,000 + directors 18,855 + rent 22,500 + insurance 3,000 + accountancy 2,400
#          + electricity 5,400 + repairs 1,800 + depreciation 4,000 + bank 405 + phone 900
#          + advertising 240                                      = 122,500.00
#   Profit per accounts                                            57,500.00
#   Add depreciation 4,000; less AIA on used lathe 1,500 (AIA limit 1,000,000 x 273/365)
#   Taxable total profits                                          60,000.00
#   Limits: upper 250,000 / 2 x 273/365 = 93,493.150... -> 93,493.15; lower 25,000 x 273/365 -> 18,698.63
#   Slices by days: profits 40,000.00 / 20,000.00; upper 62,328.77 / 31,164.38
#   Tax at 25%: 10,000.00 + 5,000.00
#   Marginal relief: (62,328.77 - 40,000) x 3/200 = 334.93155 -> 334.93
#                    (31,164.38 - 20,000) x 3/200 = 167.4657  -> 167.47
#   CT = 15,000.00 - 502.40 = 14,497.60
# ---------------------------------------------------------------------------------------------
def test_client3_marginal_relief_short_period_associates(by_id):
    c = by_id["c03-northgate"]
    comp = c["computation"]
    assert c["period"]["days"] == 273
    assert comp["accounting_profit"] == P("57500.00")
    assert comp["ttp"] == P("60000.00")
    assert c["ca"]["aia_limit"] == P("747945.21")          # 1,000,000 x 273/365 = 747,945.205...
    sl = comp["schedule"]["slices"]
    assert [s["days"] for s in sl] == [182, 91]
    assert [s["upper"] for s in sl] == [P("62328.77"), P("31164.38")]
    assert sum(s["upper"] for s in sl) == P("93493.15")
    assert sum(s["lower"] for s in sl) == P("18698.63")
    assert [(s["n"], s["tax"], s["mr"]) for s in comp["slices"]] == [
        (P("40000.00"), P("10000.00"), P("334.93")), (P("20000.00"), P("5000.00"), P("167.47"))]
    assert comp["liability"] == P("14497.60")
    assert any(r["rule_id"] == "CA-AIA-02" for r in c["review"])     # AIA shared with the associate?
    assert c["extraction"]["default"]["result"]["ea_eligible"]       # two directors paid above ST


# ---------------------------------------------------------------------------------------------
# Client 4 - Ridgeway Joinery Ltd, year to 31 March 2026 (FY2025).
#
#   Sales 900,000.00; costs 560,055.50 (materials 264,000, wages 120,000, director 12,570,
#   employer NIC 6,385.50, rent 48,000, power 18,000, insurance 9,600, car lease 5,400, motor 6,000,
#   legal 5,000, accountancy 4,200, repairs 7,000, depreciation 45,000, advertising 3,000,
#   prototype materials 3,500, bank 600, phone 1,800)
#   Profit per accounts                                            339,944.50
#   Less: car lease VAT posted to the VAT account but 50% blocked: 12 x 45 = 540.00
#   Add: depreciation 45,000; capital legal fees 5,000;
#        car lease 15% (CO2 120 > 50) x (5,400 + 540) = 891.00            50,891.00
#   Capital allowances:
#     CNC router new      full expensing                          120,000.00
#     Electrical (integral feature) AIA                             10,000.00
#     Forklift used       AIA                                       18,000.00
#     Main pool: 40,000 b/f - 3,000 van disposal = 37,000 x 18%      6,660.00
#     Special pool: car 32,000 (95g/km) x 6%                         1,920.00
#     SBA: 200,000 x 3% x 182/365 (from 1 Oct 2025)                  2,991.78  (2,991.7808)
#     Total                                                        159,571.78
#   Taxable total profits 339,944.50 - 540 + 50,891 - 159,571.78 = 230,723.72
#   Marginal relief band: 230,723.72 x 25% = 57,680.93
#     less (250,000 - 230,723.72) x 3/200 = 289.1442 -> 289.14            CT = 57,391.79
# ---------------------------------------------------------------------------------------------
def test_client4_capital_allowances(by_id):
    c = by_id["c04-ridgeway"]
    comp, ca = c["computation"], c["ca"]
    assert comp["accounting_profit"] == P("339944.50")
    assert line(c, "vat_blocked")["amount"] == -P("540.00")
    assert line(c, "addback_EXP-CAR-01")["amount"] == P("891.00")
    assert line(c, "addback_EXP-LEGAL-02")["amount"] == P("5000.00")
    amounts = {l["key"]: l["amount"] for l in ca["lines"]}
    assert amounts["ca_fe"] == P("120000.00")
    assert amounts["ca_aia"] == P("28000.00")
    assert amounts["ca_wda_main"] == P("6660.00")
    assert amounts["ca_wda_special"] == P("1920.00")
    assert amounts["ca_sba_A5"] == P("2991.78")
    assert ca["allowances"] == P("159571.78")
    assert ca["pools_cf"] == {"main": P("30340.00"), "special": P("30080.00")}
    assert comp["ttp"] == P("230723.72")
    assert comp["liability"] == P("57391.79")
    assert c["vat"]["overclaimed"]["amount"] == P("540.00")
    rules = {r["rule_id"] for r in c["review"]}
    assert {"AA-SETTLE-01", "CT-RD-01"} <= rules


# ---------------------------------------------------------------------------------------------
# Client 5 - Kestrel Data Ltd, IT contractor, year to 30 June 2026 (FY2025 274 days, FY2026 91).
#
#   Sales 12 x 9,000 + 2,000                                      110,000.00
#   Costs: salary 12,570 + employer NIC 1,135.50 + accountancy 1,500 + insurance 500 + software 600
#          + rail fares 2,400 + use of home 1,200 + depreciation 600   = 20,505.50
#   Profit per accounts                                             89,494.50
#   Add depreciation 600; less full expensing on laptop 1,800
#   Taxable total profits                                           88,294.50
#   Use of home (EXP-HOME-02) is a judgment: provisionally allowed, routed to review.
#   Slices (pence): profits 8,829,450 x 274/365 = 6,628,135.07 -> 6,628,135; remainder 2,201,315
#                   upper 25,000,000 x 274/365 = 18,767,123.29 -> 18,767,123; remainder 6,232,877
#   Tax 25%: 1,657,033.75 -> 1,657,034;  550,328.75 -> 550,329
#   MR: (18,767,123 - 6,628,135) x 3/200 = 182,084.82 -> 182,085
#       (6,232,877 - 2,201,315) x 3/200 = 60,473.43 -> 60,473
#   CT = 1,657,034 + 550,329 - 182,085 - 60,473 = 1,964,805 pence = 19,648.05
#   (On the whole period unsliced the figure is 19,648.0425; per-slice rounding gives the extra penny.)
# ---------------------------------------------------------------------------------------------
def test_client5_contractor(by_id):
    c = by_id["c05-kestrel"]
    comp = c["computation"]
    assert comp["accounting_profit"] == P("89494.50")
    assert comp["ttp"] == P("88294.50")
    assert [(s["n"], s["tax"], s["mr"]) for s in comp["slices"]] == [(6628135, 1657034, 182085), (2201315, 550329, 60473)]
    assert comp["liability"] == P("19648.05")
    assert comp["provisional"]
    kinds = {r["rule_id"]: r for r in c["review"]}
    assert "EXT-IR35-01" in kinds and "EXP-HOME-02" in kinds
    assert kinds["EXP-HOME-02"]["status"] == "open" and kinds["EXT-IR35-01"]["status"] == "open"
    # Scottish taxpayer: Scottish non-savings bands in the planning model
    assert c["extraction"]["model"]["people"][0]["ns_bands"][0]["rate_bp"] == 1900
    # FRS: computer consultancy, but goods are under 2% -> limited cost trader at 16.5%
    assert c["vat"]["frs"]["limited_cost_trader"] and c["vat"]["frs"]["flat_rate_bp"] == 1650


# ---------------------------------------------------------------------------------------------
# Client 6 - Tom Hargreaves Plumbing & Heating, sole trader, Wales, 2025-26.
#
#   Sales 12 x 12,500                                             150,000.00
#   Expenses 68,820.00 (materials 45,000, subcontract 12,000, van 4,000, phone 600, insurance 1,800,
#            accountancy 1,200, advertising 1,000, depreciation 2,800, entertaining 200, fine 100, home 120)
#   Net profit per accounts                                         81,180.00
#   Add: van private 10% x 4,000 = 400; phone private 25% x 600 = 150   550.00
#   Add: depreciation 2,800; entertaining 200; speeding fine 100     3,100.00
#   Use of home 25-50 hours: £10 x 12 = 120 = booked -> no adjustment
#   Less: van (used, 10% private use) AIA 14,000 in a single-asset pool x 90% = (12,600.00)
#   Taxable trading profit                                          72,230.00
#   Income tax (Welsh rates = rUK totals): 72,230 - 12,570 = 59,660; 7,540.00 + 21,960 x 40% 8,784.00 = 16,324.00
#   Class 4: 2,262.00 + (72,230 - 50,270) x 2% 439.20 = 2,701.20;  total 19,025.20
#   VAT: standard 30,000 output - 12,240 input = 17,760; FRS 9.5% x 180,000 = 17,100; saving 660
#   MTD: 2024-25 turnover 138,000 > 50,000 -> mandated from 2026-27; no software recorded.
# ---------------------------------------------------------------------------------------------
def test_client6_sole_trader_wales(by_id):
    c = by_id["c06-hargreaves"]
    comp = c["computation"]
    assert comp["accounting_profit"] == P("81180.00")
    assert line(c, "addback_EXP-PRIV-01")["amount"] == P("550.00")
    assert c["ca"]["allowances"] == P("12600.00")
    assert comp["taxable_profit"] == P("72230.00")
    assert comp["income_tax"] == P("16324.00")
    assert comp["class4"] == P("2701.20")
    assert comp["liability"] == P("19025.20")
    frs = c["vat"]["frs"]
    assert (frs["standard"], frs["flat_rate"], frs["saving"]) == (P("17760.00"), P("17100.00"), P("660.00"))
    assert c["sa"]["mtd"]["mandated_now"] and c["sa"]["mtd"]["mandated_from"] == "2026-27"
    assert any(f["rule"] == "SA-MTD-01" and f["severity"] == "serious" for f in c["flags"])
