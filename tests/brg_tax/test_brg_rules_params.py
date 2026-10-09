"""Rules validator, parameter loader and the GOV.UK verification check."""
import json
import shutil
from datetime import date

import pytest
import yaml

from brg_tax.dates import add_months, fy_slices, tax_year_of
from brg_tax.money import at_rate, muldiv, to_pence
from brg_tax.params import MissingParam, ParamStore
from brg_tax.params_update import check, update
from brg_tax.rules import RuleBook, RuleError, validate


def test_library_is_valid(book, store):
    assert validate(book, store) == []


def test_every_rule_has_authority_and_judgments_have_factors(book):
    for r in book.rules:
        assert r.authority, r.id
        if r.certainty == "judgment":
            assert r.factors and r.authorities and r.default, r.id


def _copy_rules(tmp_path, book_dir):
    d = tmp_path / "rules"
    shutil.copytree(book_dir, d, ignore=shutil.ignore_patterns("*.py", "__pycache__"))
    return d


def test_rule_without_authority_fails(tmp_path):
    from brg_tax.rules import RULES_DIR
    d = _copy_rules(tmp_path, RULES_DIR)
    doc = yaml.safe_load((d / "income.yaml").read_text())
    doc["rules"][0]["authority"] = []
    (d / "income.yaml").write_text(yaml.safe_dump(doc))
    with pytest.raises(RuleError, match="authority"):
        RuleBook.load(d)


def test_overlapping_dates_and_missing_params_are_reported(tmp_path, store):
    from brg_tax.rules import RULES_DIR
    d = _copy_rules(tmp_path, RULES_DIR)
    doc = yaml.safe_load((d / "income.yaml").read_text())
    dup = dict(doc["rules"][0])
    dup["effective"] = {"from": "2020-01-01", "to": None}
    bad = dict(doc["rules"][1])
    bad["id"] = "INC-TEST-99"
    bad["params"] = ["no.such.param"]
    doc["rules"] += [dup, bad]
    (d / "income.yaml").write_text(yaml.safe_dump(doc))
    problems = validate(RuleBook.load(d), store, check_engine=False)
    text = " ".join(p["problem"] for p in problems)
    assert "overlapping effective dates" in text
    assert "parameter no.such.param missing" in text


def test_params_resolve_by_tax_year_and_financial_year(store):
    # VAT threshold sits in the financial-year block: 85k to 31 March 2024, 90k from 1 April 2024
    assert store.value("vat.registration_threshold", date(2024, 3, 31)) == 85000
    assert store.value("vat.registration_threshold", date(2024, 4, 1)) == 90000
    # dividend allowance is tax-year: 2023-24 runs to 5 April 2024
    assert store.value("it.dividend_allowance", date(2024, 4, 5)) == 1000
    assert store.value("it.dividend_allowance", date(2024, 4, 6)) == 500
    # effective_from inside a year
    assert store.value("ca.ct.fya_main_40_rate", date(2025, 12, 31)) is None
    assert store.value("ca.ct.fya_main_40_rate", date(2026, 1, 1)) == 40
    with pytest.raises(MissingParam):
        store.get("ct.main_rate", date(2030, 4, 1))


def test_every_year_has_every_key(store):
    keys = {y: set(f.params) for y, f in store.files.items()}
    common = set.intersection(*keys.values())
    for y, k in keys.items():
        assert k - common <= {"ca.ct.fya_main_40_rate", "ca.it.fya_main_40_rate"}, y


def test_every_param_has_source_and_authority(store):
    for y, f in store.files.items():
        for k, e in f.params.items():
            assert e["source_url"].startswith("https://www.gov.uk/"), (y, k)
            assert e["authority"], (y, k)
            assert "verified" in e and "retrieved" in e, (y, k)


def test_verification_check_near_window():
    page = "Registration threshold. The VAT threshold is £90,000 from 1 April 2024. " + "x " * 500 + "£85,000 elsewhere"
    assert check(page, "£90,000", "threshold") is None
    assert "not found" in check(page, "£95,000", "threshold")
    assert "not within" in check(page, "£85,000", "Registration threshold")


def test_params_update_marks_verified_with_fake_fetcher(tmp_path):
    from brg_tax.params import PARAMS_DIR
    src = PARAMS_DIR / "2025-26.json"
    shutil.copy(src, tmp_path / "2025-26.json")

    def fake(url):
        if "vat-registration" in url:
            return "<html><body><p>You must register if your VAT taxable turnover is more than the threshold of &pound;90,000.</p></body></html>"
        raise OSError("offline")

    summary = update(directory=tmp_path, fetcher=fake, today=date(2026, 10, 9))
    doc = json.loads((tmp_path / "2025-26.json").read_text())
    e = doc["params"]["vat.registration_threshold"]
    assert e["verified"] is True and e["retrieved"] == "2026-10-09"
    assert doc["params"]["ct.main_rate"]["verified"] is False
    assert "fetch failed" in doc["params"]["ct.main_rate"]["verify_result"]
    assert summary["2025-26"]["verified"] == 1


def test_money_and_dates():
    assert to_pence("£1,234.56") == 123456 and to_pence("(12.00)") == -1200 and to_pence(5) == 500
    assert muldiv(5, 1, 2) == 3 and muldiv(-5, 1, 2) == -3          # half-up, away from zero
    assert at_rate(866295_50 // 100, 1900) == at_rate(866295, 1900)
    assert add_months(date(2026, 6, 30), 9) == date(2027, 3, 31)       # month-end rule
    assert add_months(date(2026, 3, 31), 9) == date(2026, 12, 31)
    assert tax_year_of(date(2026, 4, 5)) == "2025-26" and tax_year_of(date(2026, 4, 6)) == "2026-27"
    assert [s[3] for s in fy_slices(date(2025, 10, 1), date(2026, 6, 30))] == [182, 91]
