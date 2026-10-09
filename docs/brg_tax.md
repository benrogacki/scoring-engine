# BRG Tax Engine

The BRG Tax Engine sends every tax decision for a UK SME client through an explicit, cited library of
rules. It produces the computations and an audit trail that links each figure to its transactions, the
rules applied, the parameters used (with tax year) and any reviewer decision. It follows the same
pattern as the Debtor Risk Desk (`scoring_engine/`):

- a Python engine driven by `policy.json` and run from a CLI
- data health checks that run before any figure is trusted
- a "changes since the last run" diff
- one self-contained HTML dashboard, whose Optimiser tab recomputes in the browser through a JS mirror
  of the engine maths

> Outputs are working papers to support professional review. They are not advice until reviewed and
> signed off.

## Quick start

```bash
pip install -e ".[tax,test]"          # pydantic, PyYAML, pytest; Python 3.11+

brg-tax check                          # validate the rules library and parameter files
brg-tax sample --out clients           # (re)write the six synthetic sample clients
brg-tax run --clients clients --policy policy.json --as-of 2026-10-09 --out out/oct
brg-tax run --clients clients --policy policy.json --decisions decisions.json \
            --previous out/oct --out out/nov
brg-tax diff out/oct out/nov
brg-tax params-update --year 2026-27   # needs access to www.gov.uk
pytest tests/brg_tax
```

Open `out/<run>/dashboard.html` in a browser. It works like the Debtor Risk Desk dashboard. Opened as a
plain file, it is a snapshot of the run. Served from a web server next to its run files (an internal
server or a private share, never a public site, because client data is confidential), it lists the
run's files and checks `run_fingerprint.txt` every 10 minutes, reloading when a newer run is published. Worked outputs for the sample clients are in
[`examples/brg_tax/output/`](../examples/brg_tax/output/); start with `summary.md`.

## Before you rely on any figure

1. **Parameters are unverified.** This build had no network access to GOV.UK, so every rate and
   threshold in `brg_tax/params/*.json` is a starting value with `verified: false`. Run
   `brg-tax params-update` on a machine with internet access. It fetches each value's cited GOV.UK page
   and marks the value verified only if the figure appears near its label. It never changes a value:
   anything it cannot confirm stays unverified, and you check and edit it by hand. Values marked
   `seed_confidence: low` need the most care. These include:
   - the 2026-27 dividend and s455 rates
   - the 14% main-rate WDA and the 40% first-year allowance
   - the 2026-27 Scottish bands, lower earnings limit and Class 2 figures
   - the official rate of interest
2. **Citations are unchecked.** Statutory and HMRC manual references were written from the
   legislation as understood. They have not been re-checked against legislation.gov.uk in this build.
   Every rules file carries `citations_checked: false` until you have reviewed it.
3. **Golden tests use the seeded values.** If a value changes after verification, re-work the
   expected figures in `tests/brg_tax/test_brg_golden.py` by hand. Don't copy them from the engine.

## Layout

```
brg_tax/
  cli.py                 brg-tax params-update | check | run | diff | sample | merge-decisions
  models.py              pydantic models: Client, Person, Transaction, Asset, DLAEntry, VatReturn, Treatment, ReviewItem, Line
  money.py, dates.py     integer-pence arithmetic (half-up), tax years, financial years, month-end rule
  ingest/                profile + bookkeeping export + FAR + DLA + VAT returns + TB; mappings/<package>.json
  rules/*.yaml           the rules library, one file per domain (readable by an accountant)
  params/<year>.json     year-versioned parameters: value, unit, authority, GOV.UK source, retrieved, verified
  params_update.py       GOV.UK verification
  engine/
    router.py            transaction facts -> matching rules -> tax and VAT treatment / review item
    capital_allowances.py, ct.py, sole_trader.py, extraction.py (optimiser + DLA monitor), vat.py, deadlines.py
    taxmath.py           pure tax arithmetic shared with dashboard/engine_mirror.js
    health.py, diff.py, run.py
  dashboard/             template.html + engine_mirror.js -> one self-contained dashboard.html
  report.py              computations/*.md, treatments.csv, review_queue.json, deadlines.ics, summary.md ...
  samples.py             the six synthetic clients
policy.json              firm-level defaults (retention, CA strategy, comparator admin cost, VAT warning level, deadline windows)
clients/<id>/            profile.json, transactions.csv, trial_balance.csv, assets.csv, dla.csv, vat_returns.csv
tests/brg_tax/           unit, golden, parity (Node) and CLI tests
```

## The three certainty levels

| Level | Meaning | Engine behaviour |
|---|---|---|
| `rule` | Mechanical treatment | Applied automatically and cited on the line. |
| `judgment` | Fact-dependent or case-law question | Never auto-resolved. Shows factors, leading authorities, a proposed default and the reasoning. Goes to the review queue. The default is used **provisionally**, and the computation is marked provisional until a decision is recorded. |
| `election` | A legitimate choice | Only these feed the optimiser: salary, dividends, employer pension, clearing a DLA by dividend, the capital allowance claim and the VAT scheme. |

Missing facts (for example entertaining with no attendees recorded) produce **fact** review items with
a prudent default. Anti-avoidance patterns produce **anti_avoidance** review items:
- s464C bed-and-breakfasting
- the settlements legislation on alphabet shares held by a non-working spouse
- dividend waivers
- the GAAR screen

The optimiser never selects any of these.

## Rules

Each rule has an `id`, `domain`, `title`, `question`, `conditions`, `outcome`, `certainty`,
`authority` (statute, required), `guidance` (HMRC manuals), `entity_types`, `effective {from, to}`,
`params` and `notes`. Judgment rules add `factors`, `authorities` (cases), `default` and `reasoning`.

Transaction rules match on facts. These come from three places:
- the nominal-code mapping
- the export's `BRG Facts` column, written as `key=value; key=value`
- the client profile

For example:

```yaml
conditions: {category: car_lease, co2_gkm: {gt: "param:ca.car_lease_co2_threshold"}}
outcome: {ct: {disallow_pct_param: ca.car_lease_disallow_pct}, vat: {recover_pct: 50}}
```

When several rules match, the one with the most conditions wins, then the higher `priority`. Tax and
VAT are chosen separately. `EXP-NORULE-01` catches anything unmatched as a judgment item.

`brg-tax check` fails the build when:
- any rule lacks an authority
- versions of the same id have overlapping dates
- a referenced parameter is missing for any year in use
- a judgment rule lacks factors, authorities or a default
- the engine cites a rule id that does not exist

## Computations

- **Router.** Covers:
  - wholly and exclusively and duality
  - capital vs revenue and repairs
  - entertaining (staff and non-staff)
  - client gifts and trivial benefits
  - car leases (15% restriction and the 50% VAT block), car purchase VAT and fuel
  - private use
  - use of home (flat rate is a rule; actual-cost apportionment is a judgment)
  - mileage at approved rates (with the 10,000-mile band per person and tax year)
  - pre-trading expenditure
  - fines and penalties
  - legal and professional fees
  - training
  - R&D costs
  - donations
  - uncategorised items

  Input tax that is blocked but was posted to the VAT account becomes part of the cost and is flagged
  as over-claimed.
- **Capital allowances.**
  - Full expensing and the 50% special-rate FYA (companies, new and unused only).
  - AIA, time-apportioned for short periods. AIA sharing with associates is a judgment.
  - The 40% FYA from 1 January 2026 (low confidence).
  - Cars by CO2, and the zero-emission FYA.
  - Main and special pools with a hybrid WDA rate across 1 April 2026.
  - The small pools allowance.
  - Single-asset pools for private use.
  - Disposals, and s45U charges on assets that were full-expensed.
  - SBA, time-apportioned by days.

  Three claim strategies are available: `max`, `aia_first` and `wda_only`.
- **Corporation tax.** Takes accounting profit, then the add-backs grouped by rule, irrecoverable
  VAT, NTLR credits, capital allowances, losses brought forward and QCDs, to reach taxable total
  profits. The tax is then worked out per financial year at the small profits rate, the main rate or
  with marginal relief. Limits are divided by (1 + associated companies) and reduced by days/365 for
  short periods. R&D is detected and routed to review, never computed.
- **Extraction optimiser.** Searches a grid of uniform director salaries, with dividends set to the
  year's post-tax profit (less policy retention). It reports:
  - CT, income tax (rest of UK, Scottish and Welsh bands for non-savings income; UK bands and rates
    for dividends; PA taper), employee and employer NIC and dividend tax
  - the Employment Allowance, including the single-director exclusion
  - the hard stop on distributable reserves
  - the pension annual allowance
  - s455 on any DLA not cleared

  The planning year is the tax year containing `--as-of`, with the CT period being the 12 months
  after the computed period. Where a financial year has no parameter file yet, the latest year's
  rates are assumed and flagged.
- **DLA monitor.** Covers:
  - the running balance and the year-end balance
  - repayments within nine months, with s464C(1) matching. Repayments by dividend, salary or bonus
    are excluded; repayments that could fall under s464C(3) are a judgment.
  - s455 at the rate when the loan was made, with its due date
  - the s458 note
  - the beneficial loan by averaging (ITEPA s182) and the alternative method (s183), with Class 1A
- **IR35.** Applies to engagements with a small or unknown client and no SDS. It goes to review with
  an estimated Chapter 8 deemed payment.
- **Sole traders.**
  - Tax-year basis: a 31 March accounting date is treated as 5 April; non-aligned periods are
    apportioned and flagged.
  - Income tax by region, and Class 4.
  - Class 2 status: payable in 2023-24, credited or voluntary from 2024-25.
  - Payments on account and the balancing payment.
  - MTD for Income Tax mandation from the qualifying-income schedule.
  - A sole trader vs company comparator that includes the extra admin cost from policy.
- **VAT.**
  - Registration: the rolling 12-month historic test (month the threshold is crossed, notify-by
    date, effective date) and the 30-day forward look.
  - Deregistration.
  - Flat rate comparison with the limited cost trader test.
  - Cash and annual accounting eligibility.
  - Partial exemption detection (out of scope for computation).
- **Deadlines.** Generated from `rules/deadlines.yaml`:
  - CT600 filing and CT payment, and s455
  - Companies House accounts and the confirmation statement
  - VAT returns by stagger
  - SA filing, balancing payment and payments on account
  - MTD quarterly updates
  - P11D, Class 1A, P60 and the final RTI submission

  Offsets use the month-end rule, so a period ending 30 June has CT due on 1 April.

## Data health checks

The checks are:
- the TB balances
- ledger profit agrees to the TB
- no uncategorised transactions
- FAR additions agree to the ledger
- the DLA schedule agrees to the TB
- VAT returns (boxes 1 and 4) agree to the ledger
- parameters exist and are verified for every year spanned
- associated-company information is present

A failed check marks the client "Blocked: data health" in every output, and `run --strict` exits
non-zero.

## Reviewer decisions

In the dashboard's Review queue, record a decision: accept the default, or override it with an
outcome such as `{"ct": "disallow"}` or `{"associated_companies": 2}`. Give the reviewer's initials
and a note. Decisions are kept in the browser and exported with **Export decisions JSON**. Pass that
file to `brg-tax run --decisions decisions.json`; the decision is then applied, the item shows as
decided, and the line is no longer provisional. Use `brg-tax merge-decisions` to combine exports.
Review ids are `client:rule:key`, so a decision survives re-runs as long as the transaction keeps its
row in the export.

## Bookkeeping exports

`ingest/mappings/{xero,quickbooks,freeagent}.json` are modelled on each package's default export
layout and chart of accounts. Check them against real client exports and add codes as needed.
Unmapped codes fail the categorisation health check. Recode a single transaction with
`category=<category>` in `BRG Facts`.

## Out of scope in v1 (detected and flagged where possible)

- R&D relief computation
- group and consortium relief
- partial exemption
- savings income
- the 2023-24 transition profit
- loss relief elections (flagged only)
- company car benefits
- carry-forward of the pension annual allowance
- quarterly instalment payments
- the transfer issues on incorporation (goodwill, CGT relief)
- the Chapter 10 off-payroll mechanics
