# Credit-Risk Scoring Engine

A scoring workflow for finance teams, built on the debtor ledger. It scores each customer on
**payment history**, **ageing** and **concentration/exposure**. From those scores it assigns a risk
grade, recommends a **credit limit** and produces a ranked **collections worklist**.

It has no dependencies beyond the Python standard library (3.9+); the optional Databricks connector
is the only extra. Inputs come from CSV exports, **NetSuite** (SuiteQL) or **Databricks** tables. Outputs are CSV and Markdown, ready for Excel, Power BI or an email to
the credit controller.

```
 debtor ledger CSV ─┐
                    ├─► features ─► sub-scores ─► composite + grade ─┬─► credit limit recommendation
 customer master ───┘  (history,    (0-100 each)   (A–E, policy caps) └─► collection priority + action
                        ageing,
                        exposure)
```

## Quick start

```bash
# 1. Try it on synthetic data
python -m scoring_engine sample --out examples --as-of 2026-09-30
python -m scoring_engine run --ledger examples/ledger.csv --customers examples/customers.csv \
       --as-of 2026-09-30 --out out

# 2. Run it on your own ledger
python -m scoring_engine run --ledger my_ledger.csv --customers my_customers.csv --out out

# open out/dashboard.html in a browser to explore the results

# optional: install the `credit-score` command
pip install -e .
credit-score run --ledger my_ledger.csv --customers my_customers.csv --config my_policy.json
```

### Pulling live data

```bash
# straight from NetSuite (SuiteQL + token-based auth; credentials in env vars)
credit-score run --source netsuite --out out/

# from Databricks, writing results back as Delta tables
credit-score run --source databricks --invoices-table main.finance.credit_ar_invoices \
       --customers-table main.finance.credit_customers --write-table-prefix main.finance.credit_risk
```

Setup steps, required permissions, the default queries and a scheduled Databricks job are in
[`docs/integrations.md`](docs/integrations.md).

Worked outputs from the sample ledger are in [`examples/output/`](examples/output/). Start with
[`portfolio_summary.md`](examples/output/portfolio_summary.md).

## Inputs

### Debtor ledger (required): one row per invoice

| Column | Required | Notes |
|---|---|---|
| `invoice_id` | ✔ | also accepts `invoice_no`, `document_no` |
| `customer_id` | ✔ | also accepts `account`, `account_code`, `debtor_id` |
| `invoice_date` | ✔ | `YYYY-MM-DD`, `DD/MM/YYYY`, `DD-MM-YYYY`, `DD Mon YYYY` |
| `due_date` | ✔ | |
| `amount` | ✔ | currency symbols, thousands separators and `(negatives)` are handled |
| `paid_date` | | blank means still open |
| `amount_paid` | | defaults to the full amount if `paid_date` is set, otherwise 0; supports part-payments |
| `disputed` | | `Y`/`yes`/`true`/`1` |

Include **settled invoices from the last 12+ months**, not just open items. Payment history is
measured from them.

### Customer master (optional)

`customer_id`, `customer_name`, `credit_limit`, `payment_terms_days` (default 30), `industry`.
If a debtor in the ledger is missing from this file, it is scored with no credit limit and flagged.

## Methodology

Every score runs from 0 to 100, and **higher means lower risk**.

### 1. Payment history (45%)
From invoices settled in the lookback window (default 12 months), plus open invoices already past
due. Open overdue items count as "at least this late", so a customer who has stopped paying is not
mistaken for a new one.

- **Value-weighted average days late.** Scores 100 at 0 days and falls to 0 at 45 days.
- **On-time rate.** The share of invoice value paid within terms plus grace (5 days). It carries 40% of this sub-score.
- **Trend penalty.** Up to 15 points are deducted if the last 3 months are slower than the prior period.
- **Thin file.** A customer with no history gets a neutral 55. A customer with fewer than 3 settled
  invoices only earns part of the credit for good behaviour.

### 2. Ageing (35%)
Open balances are bucketed as *Not due / 1-30 / 31-60 / 61-90 / 90+*. Each bucket has a severity
weight (0, 0.2, 0.5, 0.8, 1.0). The score is `100 × (1 − severity-weighted share)`, less a penalty
for disputed balances.

### 3. Concentration & exposure (20%)
- **Share of total receivables.** Scores 100 at 0% and falls to 0 at 15% of the ledger.
- **Credit-limit utilisation.** Scores 100 up to 75% utilised and falls to 0 at 125%.

The two are averaged. If the customer has no limit on file, share alone is used. The summary also
reports the portfolio **HHI** and the top-10 debtor share.

### Grades and policy overrides

| Grade | Score | Meaning |
|---|---|---|
| A | ≥ 80 | Low risk |
| B | 65–79 | Moderate risk |
| C | 50–64 | Elevated risk |
| D | 35–49 | High risk |
| E | < 35 | Severe risk |

Hard caps are applied after scoring, so one bad signal can't be averaged away:
- 90+ day arrears ≥ 25% of the balance caps the grade at **D**. Any material 90+ balance caps it at **C**.
- A balance ≥ 120% of the credit limit caps the grade at **C**.

Every customer gets **plain-English risk drivers**, for example *"Pays on average 28 days late;
Deteriorating: paying 34 days later than prior period; Over credit limit (175% utilised)"*. Credit
committee can see why a grade was given.

### Credit limit recommendation

```
limit = avg monthly sales × (payment terms + 15 buffer days) / 30 × grade multiplier
        A 1.5 · B 1.25 · C 1.0 · D 0.6 · E 0 (suspend: cash with order)
```

- Only grades A and B may be increased, by at most 50% per review.
- Customers already holding ≥ 15% of the ledger are held at their current limit (concentration cap).
- A change within ±10% is reported as *Maintain*, to avoid churn.
- Actions: *Increase / Reduce / Maintain / Set limit / Suspend*. Any action gets a *currently over limit* flag where it applies.

### Collection priority

`priority = Σ overdue by bucket × urgency (1-30: 1.0, 31-60: 1.5, 61-90: 2.5, 90+: 4.0) × (1 + (100 − score)/100)`

Customers are tiered first, then ranked by priority score within each tier:

| Tier | Trigger | Recommended action |
|---|---|---|
| P1 | 90+ balance, or grade E | Escalate: stop supply, final demand, consider agency/legal referral |
| P2 | 61-90 balance, or grade D | Senior call + formal demand letter; agree dated payment plan |
| P3 | 31-60 balance | Phone call to AP; confirm payment date |
| P4 | 1-30 only, or below materiality | Automated reminder / statement |

Disputed balances add *"resolve dispute"* to the action.

## Outputs

| File | Contents |
|---|---|
| `scorecard.csv` | One row per customer: grade, composite and sub-scores, ageing buckets, days late, trend, share of AR, utilisation, recommended limit and action, collection tier and rank, risk drivers |
| `collections_worklist.csv` | Overdue customers in work order, with tier, overdue split, priority score and action |
| `portfolio_summary.md` | Management summary: headline KPIs, ageing profile, grade distribution, largest exposures, top of worklist, limit changes |
| `portfolio_summary.json` | The same KPIs in machine-readable form, for dashboards and month-on-month tracking |
| `dashboard.html` | Interactive dashboard (open in any browser, no install): risk map, grade mix, ageing, searchable customer table with drill-down, collections worklist with tick-off, limit recommendations, and a **Policy** tab that re-scores the ledger live as you move the sliders and exports the resulting `--config` JSON |

## Tuning the policy

Every weight, threshold and rule is configurable. Copy [`config/default.json`](config/default.json),
keep only the keys you want to change and pass `--config`. For example, a stricter policy for a
construction book:

```json
{
  "weights": {"payment": 0.4, "ageing": 0.4, "concentration": 0.2},
  "payment_history": {"days_late_floor": 30},
  "credit_limits": {"grade_multipliers": {"A": 1.25, "B": 1.0, "C": 0.8, "D": 0.5, "E": 0}},
  "collections": {"min_balance": 1000}
}
```

Weights must sum to 1.0. The engine checks this, and the grade ordering, before it runs.

## Suggested monthly workflow

1. At month-end, export the debtor ledger (open and settled items, 12–15 months) and the customer master.
2. Run `credit-score run --as-of <month-end>`.
3. **Credit control** works `collections_worklist.csv` from the top, P1 first.
4. **Credit committee** reviews the limit recommendations and signs off increases for A/B customers and suspensions for E.
5. **FD/CFO** receives `portfolio_summary.md`. Keep each month's `portfolio_summary.json` to track
   overdue %, the AR-weighted score and HHI over time.

## Global Freight Activity Tracker (separate module)

`freight_nowcast/` is a separate tool in the same repository. It tracks real-economy momentum from
published freight series:

- **road:** the German truck toll mileage index from Destatis GENESIS, monthly plus working-daily
- **sea:** OECD AIS port calls and the Baltic Dry Index, plus optional aisstream.io port counts

It produces a composite index, z-scores per geography, cycle phases and turning-point flags.
Validation is built in: toll mileage is tested against manufacturing production, and port calls
against trade statistics. It does not touch the ledger or scoring code. It feeds the capstone
through `capstone_feed.json`: the real-economy read next to the yield curve in Tier 1, and the
cycle/sector tilt in Tier 2.

```bash
python -m freight_nowcast live --out out/freight/live                      # real data: fetch + run
python -m freight_nowcast demo --as-of 2026-09-30 --out out/freight-demo   # synthetic sandbox, offline
```

Geographies: Germany, Eurozone, United States, Arabia (GCC) and world sea trade. A GitHub Actions job
checks every source every 3 hours. When a source has released new data, it republishes the nowcast to
the `freight-live` branch and to the dashboard website (Cloudflare Pages or GitHub Pages; see
[hosting](docs/freight_nowcast.md#running-live)).

See [`docs/freight_nowcast.md`](docs/freight_nowcast.md) for sources, method, validation and the
feed schema, and [`examples/freight/output/`](examples/freight/output/) for a demo run.

## Development

```bash
python -m unittest discover -s tests -v
```

The code lives in the `scoring_engine/` package:
- `loader.py`: row validation and column aliases, shared by every source
- `sources/`: NetSuite (SuiteQL, OAuth 1.0a) and Databricks (SQL connector, Spark, write-back), plus the default queries
- `features.py`: per-customer measurements
- `scoring.py`: sub-scores, grades, overrides and explanations
- `limits.py`: credit limit recommendations
- `collection.py`: collection priority
- `engine.py`: the pipeline and portfolio summary
- `report.py`: output files
- `cli.py`: the command-line interface

The freight nowcaster lives in `freight_nowcast/`; see its [docs](docs/freight_nowcast.md).
