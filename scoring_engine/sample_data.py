"""Generate a realistic synthetic debtor ledger for demos and testing."""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Tuple

# (archetype, count, monthly invoices, invoice size range, typical days late range)
ARCHETYPES = [
    ("prompt", 14, (2, 4), (2_000, 12_000), (-5, 3)),
    ("slow", 8, (1, 3), (1_500, 9_000), (15, 40)),
    ("deteriorating", 4, (2, 3), (3_000, 10_000), (0, 5)),
    ("delinquent", 3, (1, 2), (2_000, 8_000), (45, 90)),
    ("key_account", 2, (6, 8), (15_000, 40_000), (0, 10)),
    ("new", 3, (1, 1), (1_000, 5_000), (0, 5)),
    ("disputed", 2, (1, 3), (2_000, 7_000), (5, 20)),
]
INDUSTRIES = ["Retail", "Construction", "Manufacturing", "Hospitality", "Logistics", "Healthcare", "Education"]
NAMES = [
    "Apex", "Birch", "Cobalt", "Delta", "Ember", "Fjord", "Granite", "Harbor", "Iris", "Juniper",
    "Keystone", "Lumen", "Meridian", "Northgate", "Orchid", "Pinnacle", "Quarry", "Redwood", "Summit",
    "Tidewater", "Umber", "Vantage", "Willow", "Xenon", "Yardley", "Zephyr", "Atlas", "Beacon", "Cedar",
    "Dune", "Everest", "Falcon", "Glacier", "Horizon", "Ironbark", "Jade",
]
SUFFIXES = ["Ltd", "Group", "Holdings", "Trading", "Services", "Partners"]


def generate(ledger_path: Path, customers_path: Path, as_of: date, seed: int = 7, months: int = 15) -> Tuple[int, int]:
    rng = random.Random(seed)
    start = as_of - timedelta(days=round(months * 30.4375))
    customer_rows, invoice_rows = [], []
    name_iter = iter(rng.sample(NAMES, len(NAMES)))
    inv_no = 100000
    cust_no = 0

    for archetype, count, per_month, size, late in ARCHETYPES:
        for _ in range(count):
            cust_no += 1
            cid = f"C{cust_no:04d}"
            terms = rng.choice([30, 30, 30, 45, 60]) if archetype != "key_account" else 60
            first = start if archetype != "new" else as_of - timedelta(days=rng.randint(40, 80))
            monthly_sales = 0.0
            n_months = 0
            d = first
            while d <= as_of - timedelta(days=3):
                n_months += 1
                for _ in range(rng.randint(*per_month)):
                    inv_date = d + timedelta(days=rng.randint(0, 27))
                    if inv_date > as_of:
                        continue
                    amount = round(rng.uniform(*size), 2)
                    monthly_sales += amount
                    due = inv_date + timedelta(days=terms)
                    age_frac = (inv_date - start).days / max(1, (as_of - start).days)
                    lo, hi = late
                    if archetype == "deteriorating" and age_frac > 0.7:
                        lo, hi = 35, 70
                    days_late = rng.randint(lo, hi)
                    paid = due + timedelta(days=days_late)
                    disputed = archetype == "disputed" and rng.random() < 0.25
                    if archetype == "delinquent" and age_frac > 0.45:
                        paid = None  # stopped paying
                    if disputed:
                        paid = None
                    if paid is not None and paid > as_of:
                        paid = None
                    amount_paid = amount if paid else 0.0
                    if paid is None and archetype == "slow" and rng.random() < 0.15:
                        amount_paid = round(amount * 0.5, 2)  # part payment on account
                    inv_no += 1
                    invoice_rows.append(
                        {
                            "invoice_id": f"INV{inv_no}",
                            "customer_id": cid,
                            "invoice_date": inv_date.isoformat(),
                            "due_date": due.isoformat(),
                            "amount": f"{amount:.2f}",
                            "amount_paid": f"{amount_paid:.2f}",
                            "paid_date": paid.isoformat() if paid else "",
                            "disputed": "Y" if disputed else "",
                        }
                    )
                d += timedelta(days=30)
            avg_month = monthly_sales / max(1, n_months)
            # Limits roughly sized to the exposure implied by terms, with some noise.
            limit_factor = {"slow": 1.1, "delinquent": 1.0, "key_account": 1.1, "new": 0.0}.get(archetype, 1.2)
            limit = round(avg_month * (terms + 15) / 30 * limit_factor * rng.uniform(0.7, 1.2), -3)
            customer_rows.append(
                {
                    "customer_id": cid,
                    "customer_name": f"{next(name_iter)} {rng.choice(SUFFIXES)}",
                    "credit_limit": f"{limit:.0f}",
                    "payment_terms_days": terms,
                    "industry": rng.choice(INDUSTRIES),
                }
            )

    invoice_rows.sort(key=lambda r: (r["invoice_date"], r["invoice_id"]))
    for path, rows in ((ledger_path, invoice_rows), (customers_path, customer_rows)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    return len(customer_rows), len(invoice_rows)
