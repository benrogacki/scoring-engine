# Running it for real: checks, evidence, changes and the feed

Every scoring run does more than score. It runs five steps in order:

```
extract ─► data health checks ─► score ─► backtest ─► compare with the last run ─► publish
             (stop if failed)              (evidence)   (what changed)              (feed, tables, dashboard)
```

The CLI, the GitHub Actions workflow and the Databricks job all run the same pipeline
(`scoring_engine/pipeline.py`), so they produce the same files.

## Data health (`data_health.json`)

The extract is checked before anyone acts on the scores. Each check returns `ok`, `info`, `warn` or
`fail`.

| Check | Fails / warns when |
|---|---|
| Invoices loaded | **fail** if the extract is empty |
| Extract is current | **warn** if the newest invoice or payment is more than 10 days before the scoring date (`health.stale_days`). A stale extract usually means the sync broke. |
| No duplicate invoices | **warn** if an invoice ID repeats, since balances would be double counted |
| Due dates after invoice dates | **warn** if any invoice is due before it was raised |
| Overpayments | **warn** if more was paid than invoiced (often unapplied cash) |
| Settled invoices have payment dates | **warn** if more than 5% of settled invoices have no payment date, because their payment behaviour can't be measured |
| Customers in the master file | **warn** if debtors are missing from the master. They're scored with no limit. |
| Agrees to AR ageing control total | **fail** if the open balance differs from `--control-total` by more than 0.5% |

What a **fail** does in each place:
- `--strict` makes the CLI exit with an error.
- The Databricks job writes its reports, but **does not update the tables**, and then fails the run.
- `--write-table-prefix` is skipped.

Downstream systems only ever see data that passed.

`credit-score probe` connects to the source, pulls the ledger and runs these checks without
scoring. Use it to test a new connection or to diagnose a failed run.

## Backtest (`backtest.json`): do the grades predict late payment?

A scorecard is only worth using if the ledger's own history backs it. The backtest re-runs the
engine as at several past dates (default: four dates, 30 days apart). It uses only what was known
on each date: payments received later count as still open. It then follows every customer with a
balance for 90 days, to see whether any invoice went **60+ days overdue unpaid**.

| Verdict | Meaning |
|---|---|
| **evidenced** | AUC ≥ 0.70 and bad rates rise from A to E (small reversals of up to 5 points between neighbouring grades are allowed as sampling noise, and are still listed) |
| **weak** | AUC ≥ 0.60, or it ranks well but the grades aren't monotonic. Review the weights before relying on limits. |
| **not evidenced** | The score doesn't separate customers who went bad. Don't use the grades until they're recalibrated. |
| **insufficient data** | Fewer than 30 customer-dates or 5 bad outcomes, or the ledger is too short (it needs 180 days of history plus the 90-day outcome window) |

AUC is the probability that a customer who went bad scored lower than one who didn't. 0.5 is a coin
toss and 1.0 is perfect. Gini = 2 × AUC − 1.

Change the window, the definition of "bad" and the thresholds under `backtest` in the config. When
you change policy weights in the dashboard's Policy tab, export them and re-run. The backtest always
uses the policy the run was scored with.

On the synthetic sample the verdict is *evidenced* (AUC 0.94). One reversal is flagged: A 4% vs B 0%.
The four A-grade customers who went bad are the sample's "deteriorating" accounts. They paid well
until recently, which is exactly the case the trend penalty and the changes list are there to catch.

## What changed (`changes.json`)

Pass the previous run's output folder with `--previous`. The Databricks job reads the previous run
from its own scorecard table automatically. Each run then lists, most severe first:

- **New P1**: a customer newly in the escalate tier
- **Downgrade** and **Upgrade**: grade moves, with the score before and after
- **Over limit** and **Back within limit**
- **Limit action**: the recommendation changed (e.g. Maintain → Reduce)
- **New customer** and **Left ledger**

`credit-score changes OLD_DIR NEW_DIR` compares any two output folders.

## The credit feed (`credit_feed.json`, schema `scoring_engine/credit_feed@1`)

This is the contract for downstream systems: the ERP (credit holds, limit changes), collections
tooling (worklist order and actions) and BI. **Consumers must check `schema`** and reject a version
they don't recognise.

```json
{
  "schema": "scoring_engine/credit_feed@1",
  "as_of": "2026-09-30",
  "generated_at": "2026-10-04T14:08:58+00:00",
  "fingerprint": "730f41a55aa1cba4",
  "source": {"kind": "netsuite", "label": "NetSuite 1234567", "extracted_at": "...", "invoice_rows": 1362},
  "data_health": "ok",
  "backtest": {"verdict": "evidenced", "auc": 0.938, "gini": 0.875, "monotonic": true},
  "portfolio": {"customers": 36, "total_outstanding": 1804429.62, "credit_holds": 5, "...": "..."},
  "changes": [{"kind": "downgrade", "customer_id": "C0023", "detail": "Downgraded B → C ..."}],
  "customers": [{
    "customer_id": "C0028", "grade": "E", "score": 16.5,
    "recommended_limit": 0, "limit_action": "Suspend", "credit_hold": true, "over_limit": true,
    "collection": {"tier": "P1", "rank": 1, "action": "Escalate: ..."},
    "risk_drivers": ["Pays on average 99 days late", "..."]
  }]
}
```

`credit_hold` is true for grade E, or for a material balance (default 500 or more) 90+ days
overdue. A consumer should not act on a feed whose `data_health` is `fail`, and should treat grades
with care when `backtest.verdict` is not `evidenced`.

## The run fingerprint (`data_fingerprint.txt`)

This is a hash of the run's results: scorecard, worklist and health status. Two runs on unchanged
data produce the same fingerprint. It's used to:

- **publish only on change.** The scheduled GitHub workflow skips publishing when nothing moved.
- **refresh the dashboard.** Served from a web server next to its files, `dashboard.html` checks the
  fingerprint every 10 minutes and reloads when a newer run lands. It also lists the run's files for
  download. Opened as a plain file, it stays a snapshot.

## Scheduled runs

**Databricks (recommended).** `databricks/credit_scoring_job.json` runs the notebook from this repo
(see [integrations](integrations.md#option-b-a-scheduled-databricks-job-run-from-this-repo-recommended)).
Each run writes:

- `<prefix>_scorecard` and `<prefix>_worklist`, one set of rows per `as_of`;
- **`<prefix>_runs`**: one row per run with the data health, backtest verdict and AUC, grade
  counts, the number of changes, and the fingerprint. Chart it to watch the ledger and the model
  over time;
- reports, the feed and the dashboard to `<volume>/<as_of>/` and `<volume>/latest/`.

**GitHub Actions** (`.github/workflows/credit-scoring.yml`):
- On every push and pull request it runs the unit tests. It then runs the sample ledger end to end
  (August, then September compared with August) and checks the feed, health, backtest and
  fingerprint. The sample dashboard is uploaded as an artifact.
- On a weekday schedule (06:17 UTC), **if you set the repository variable `CREDIT_SOURCE`** to
  `netsuite` or `databricks`, it pulls the live ledger, probes it, scores it with `--strict`,
  compares with the last published run, and publishes only if the fingerprint changed. Secrets and
  variables are listed at the top of the workflow file.

### Why live results are never on a public website

The freight nowcaster in this repo publishes public statistics to a public site. **Customer credit
data is confidential**, so this workflow deliberately does not:
- commit live outputs to git;
- deploy them to GitHub Pages or Cloudflare Pages. GitHub Pages sites are public on most plans.

Live results go to:
- **private workflow artifacts**, kept 30 days and visible only to people with read access to the
  repository;
- **Databricks tables and Volumes**, governed by Unity Catalog grants.

The job summary on the workflow run page is **aggregate only**: counts, totals and verdicts, with
no customer names. A test enforces this.

To share the self-refreshing dashboard, serve the Volume's `latest/` folder from an internal,
access-controlled host, e.g. SharePoint, an intranet server, or Cloudflare Pages behind Cloudflare
Access. Don't use a public URL.
