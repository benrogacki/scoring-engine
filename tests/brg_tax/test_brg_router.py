"""Expense and VAT treatment router: one test per rule family."""
from datetime import date

from brg_tax.engine import router
from helpers import client, ctx, txn


def route_one(c, t, decisions=None):
    x = ctx(c, decisions)
    out = router.route(x, [t], date(2025, 4, 1), date(2026, 3, 31))
    return out[0], x


VAT_CO = client(vat={"registered": True, "registration_date": "2020-01-01"})


def test_entertaining_non_employees_disallowed_and_vat_blocked():
    t, _ = route_one(VAT_CO, txn("entertainment", 60000, 12000, attendees="includes_non_employees"))
    assert t.ct == "disallow" and t.disallowed == 60000 + 12000      # blocked VAT becomes cost
    assert t.vat_treatment == "blocked" and t.vat_recoverable == 0
    assert t.rules[0] == "EXP-ENT-01"


def test_staff_entertaining_allowed():
    t, _ = route_one(VAT_CO, txn("entertainment", 14000, 2800, attendees="staff_only"))
    assert t.ct == "allow" and t.vat_recoverable == 2800


def test_missing_attendees_goes_to_review_with_prudent_default():
    t, x = route_one(VAT_CO, txn("entertainment", 10000))
    assert t.provisional and t.ct == "disallow"
    assert x.review[0].kind == "fact" and x.review[0].rule_id == "EXP-ENT-00"


def test_reviewer_decision_overrides_default():
    c = VAT_CO
    t0, x0 = route_one(c, txn("entertainment", 10000))
    rid = x0.review[0].id
    t, _ = route_one(c, txn("entertainment", 10000), {rid: {"decision": "override", "outcome": {"ct": "allow"}, "reviewer": "BR"}})
    assert t.ct == "allow" and not t.provisional and t.decision["reviewer"] == "BR"


def test_client_gifts():
    ok, _ = route_one(VAT_CO, txn("client_gifts", 24000, 4800, carries_logo="yes", gift_type="other", cost_per_recipient=12))
    assert ok.ct == "allow"
    food, _ = route_one(VAT_CO, txn("client_gifts", 24000, 4800, carries_logo="yes", gift_type="food_drink_tobacco", cost_per_recipient=12))
    assert food.ct == "disallow" and food.vat_treatment == "recover"     # output tax on gifts is flagged by the VAT module
    big, _ = route_one(VAT_CO, txn("client_gifts", 24000, 4800, carries_logo="yes", gift_type="other", cost_per_recipient=80))
    assert big.ct == "disallow"


def test_car_lease_restriction_and_vat_block():
    t, _ = route_one(VAT_CO, txn("car_lease", 45000, 9000, co2_gkm=120))
    assert t.vat_recoverable == 4500 and t.amount == 49500
    assert t.disallowed == 7425 and t.allowable == 49500 - 7425         # 15% of 495.00
    low, _ = route_one(VAT_CO, txn("car_lease", 45000, 9000, co2_gkm=40))
    assert low.disallowed == 0


def test_mileage_bands_across_the_year_for_sole_trader():
    st = client("sole_trader", package="freeagent")
    x = ctx(st)
    t1 = txn("mileage", 450000, d=date(2025, 6, 1), business_miles=9000)
    t2 = txn("mileage", 120000, d=date(2025, 9, 1), business_miles=3000)
    t2 = t2.model_copy(update={"id": "x:m2"})
    out = router.route(x, [t1, t2], date(2025, 4, 1), date(2026, 3, 31))
    assert out[0].allowable == 9000 * 45
    # second claim: 1,000 miles at 45p + 2,000 at 25p = 950.00 allowed of 1,200 claimed
    assert out[1].allowable == 1000 * 45 + 2000 * 25 and out[1].disallowed == 120000 - 95000


def test_use_of_home_flat_rate_and_judgment():
    st = client("sole_trader", package="freeagent")
    t, _ = route_one(st, txn("use_of_home", 40000, method="flat_rate", hours_per_month=60))
    assert t.allowable == 18 * 100 * 12 and t.disallowed == 40000 - 21600
    j, x = route_one(st, txn("use_of_home", 40000))
    assert j.provisional and x.review[0].rule_id == "EXP-HOME-02" and x.review[0].kind == "judgment"


def test_pre_trading_window():
    st = client("sole_trader", package="freeagent", sole_trader={"trading_start": "2025-06-01"})
    ok, _ = route_one(st, txn("software", 10000, d=date(2025, 5, 1)))
    assert ok.ct == "allow" and "EXP-PRE-01" in ok.rules
    st2 = client("sole_trader", package="freeagent", sole_trader={"trading_start": "2033-06-01"})
    old, _ = route_one(st2, txn("software", 10000, d=date(2025, 5, 1)))
    assert old.disallowed == 10000


def test_fines_legal_capital_repairs():
    co = client()
    assert route_one(co, txn("fines_penalties", 6000, fine_liability="business"))[0].disallowed == 6000
    assert route_one(co, txn("fines_penalties", 6000, fine_liability="employee"))[0].ct == "allow"
    assert route_one(co, txn("legal_professional", 500000, fee_nature="capital"))[0].disallowed == 500000
    lg, x = route_one(co, txn("legal_professional", 500000))
    assert lg.provisional and x.review[0].rule_id == "EXP-LEGAL-03"
    assert route_one(co, txn("repairs", 100000, improvement="yes"))[0].disallowed == 100000
    assert route_one(co, txn("repairs", 100000))[1].review[0].rule_id == "EXP-CAP-02"


def test_trivial_benefits_and_unregistered_vat():
    co = client()
    t, _ = route_one(co, txn("staff_gifts", 4000, cost_per_recipient=40, cash_or_voucher="no"))
    assert t.rules[0] == "EXP-TRIV-01" and t.vat_treatment == "not_registered"


def test_uncategorised_and_no_rule():
    co = client()
    u, x = route_one(co, txn("uncategorised", 5000))
    assert u.disallowed == 5000 and x.review[0].rule_id == "EXP-UNCAT-01"
    s, x2 = route_one(co, txn("sundry", 5000))
    assert s.provisional and x2.review[0].rule_id == "EXP-WE-01"
