# Connecting NetSuite and Databricks

The engine can read the debtor ledger from three places. All three produce the same outputs.

| Source | Use when | Command |
|---|---|---|
| CSV | Testing, or ad-hoc exports | `credit-score run --ledger ledger.csv --customers customers.csv` |
| NetSuite | You want to pull live from the ERP | `credit-score run --source netsuite` |
| Databricks | NetSuite is already synced to your lakehouse, or you want results as tables | `credit-score run --source databricks --invoices-table …` |

Two things apply to every source:
- Each one passes through the same validation as the CSV path.
- `credit-score extract` pulls the data to CSV without scoring it. Use it to check the extract against the AR ageing report, or to keep an audit copy of what was scored.

```
NetSuite ──SuiteQL──┐                              ┌─► out/ (CSV, Markdown, dashboard.html)
                    ├─► credit-score run ──────────┤
Databricks ──SQL────┘   (same loader + engine)     └─► Databricks tables <prefix>_scorecard / _worklist
```

---

## 1. NetSuite (SuiteQL over REST)

### One-off setup (NetSuite administrator, about 20 minutes)

1. **Enable features.** Go to *Setup → Company → Enable Features → SuiteCloud* and tick
   **REST Web Services** and **Token-Based Authentication**.
2. **Create a role**, e.g. *Credit Scoring (read-only)*, with these permissions:
   - Setup → **REST Web Services** (Full) and **Log in using Access Tokens** (Full)
   - Transactions → **Invoice**, **Customer Payment**, **Credit Memo**, **Find Transaction** (View)
   - Lists → **Customers** (View)

   Also restrict the role to the subsidiaries you want scored.
3. **Create an integration record.** Go to *Setup → Integration → Manage Integrations → New*, name it
   "Credit scoring engine" and tick **Token-Based Authentication**. Leave the OAuth 2.0 boxes
   unticked. When you save, NetSuite shows the **Consumer Key / Secret** once, so copy them then.
4. **Create an access token.** Go to *Setup → Users/Roles → Access Tokens → New* and pick the
   integration, a service user and the role from step 2. NetSuite shows the **Token ID / Secret**
   once, so copy them then.
5. **Find your account ID.** It's under *Setup → Company → Company Information* (e.g. `1234567`; a
   sandbox is `1234567_SB1`).

### Configure and run

Keep credentials in environment variables or a secrets manager. Never put them in the repo.

```bash
export NETSUITE_ACCOUNT_ID=1234567
export NETSUITE_CONSUMER_KEY=...
export NETSUITE_CONSUMER_SECRET=...
export NETSUITE_TOKEN_ID=...
export NETSUITE_TOKEN_SECRET=...

credit-score extract --source netsuite --out data/      # check what comes back first
credit-score run --source netsuite --as-of 2026-09-30 --currency £ --out out/
```

### What it queries (and what to check)

The default queries are in `scoring_engine/sources/queries/`:

- `netsuite_invoices.sql` pulls **customer invoices** from the last 15 months (`--lookback-months`):
  - Amounts are converted to base currency at the invoice exchange rate.
  - The open balance comes from `foreignamountremaining`.
  - `paid_date` is the latest payment, credit memo or journal applied to the invoice
    (via `NextTransactionLink`).
- `netsuite_customers.sql` pulls the **customer master**: credit limit, the term's
  `daysuntilnetdue` and the customer category (used as the industry).

Check these against your account before relying on the scores:

- **Disputes.** NetSuite has no standard dispute field. The query reads `custbody_disputed`.
  Change it to your custom field, or to `'F' AS disputed` if you don't track disputes.
- **Subsidiaries and currency.** If you score one legal entity, add `AND t.subsidiary = <id>`.
- **Reconcile.** Run `extract`, then compare the total of `amount_remaining` against the NetSuite
  *A/R Aging Summary* for the same date. They should match to the penny.

To use your own queries, copy the files, edit them and pass
`--invoices-query my_invoices.sql --customers-query my_customers.sql`. Keep the output column names
the same, because the engine recognises them.

---

## 2. Databricks

### Option A: run from anywhere against a SQL warehouse

```bash
pip install "scoring-engine[databricks]"      # adds databricks-sql-connector
export DATABRICKS_SERVER_HOSTNAME=adb-1234567890123456.7.azuredatabricks.net
export DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/abc123def456    # warehouse → Connection details
export DATABRICKS_TOKEN=...                                     # service principal token recommended

credit-score run --source databricks \
  --invoices-table main.finance.credit_ar_invoices \
  --customers-table main.finance.credit_customers \
  --write-table-prefix main.finance.credit_risk \
  --out out/
```

`--write-table-prefix` writes two Delta tables: `main.finance.credit_risk_scorecard` and
`main.finance.credit_risk_worklist`.
- Each run is stored with its `as_of` date. Re-running a date replaces that date's rows, so history
  builds up month by month.
- Point Power BI or a Databricks SQL dashboard at these tables for trend reporting.
- `--write-table-prefix` also works with `--source netsuite`: pull from NetSuite and land the
  results in Databricks.

The account needs `SELECT` on the source views and `CREATE TABLE`/`MODIFY` on the target schema.

### Option B: a scheduled Databricks job (no tokens)

`databricks/credit_scoring_job.py` is a Databricks notebook. It reads the tables with Spark, scores
them, writes the Delta tables and saves the reports and `dashboard.html` to a Unity Catalog Volume.

1. Add this repo to the workspace as a **Git folder** (*Workspace → Create → Git folder*). The
   engine is pure Python, so there's nothing to install.
2. Open `databricks/credit_scoring_job.py` and fill in the widgets. Run it once by hand.
3. Go to *Workflows → Create job*, add a notebook task pointing at the file, pass the same
   parameters, and schedule it (e.g. 06:00 on the 2nd of each month, after month-end close).
4. Optional: use `policy_json` to pass a policy exported from the dashboard's Policy tab.

### The curated views the defaults expect

The default Databricks queries read two views with the engine's own column names. That keeps the
engine independent of how NetSuite lands in the lakehouse (Fivetran, Celigo, SuiteAnalytics
Connect, and so on).

Here is an example over a raw NetSuite sync. The table and column names below follow NetSuite's
record names, so **rename them to match your sync tool's schema**:

```sql
CREATE OR REPLACE VIEW main.finance.credit_ar_invoices AS
SELECT
  CAST(t.id AS STRING)                                   AS invoice_id,
  CAST(t.entity AS STRING)                               AS customer_id,
  CAST(t.trandate AS DATE)                               AS invoice_date,
  CAST(COALESCE(t.duedate, t.trandate) AS DATE)          AS due_date,
  t.foreigntotal * COALESCE(t.exchangerate, 1)           AS amount,
  COALESCE(t.foreignamountremaining, 0) * COALESCE(t.exchangerate, 1) AS amount_remaining,
  CAST(pay.last_payment_date AS DATE)                    AS paid_date,
  COALESCE(t.custbody_disputed = 'T', false)             AS disputed
FROM netsuite.transaction t
LEFT JOIN (
  SELECT l.previousdoc AS invoice_id, MAX(n.trandate) AS last_payment_date
  FROM netsuite.nexttransactionlink l
  JOIN netsuite.transaction n ON n.id = l.nextdoc
  WHERE n.type IN ('CustPymt', 'CustCred', 'Journal')
  GROUP BY l.previousdoc
) pay ON pay.invoice_id = t.id
WHERE t.type = 'CustInvc' AND t.posting = 'T' AND t.voided = 'F'
  AND COALESCE(t._fivetran_deleted, false) = false;       -- drop if your tool doesn't soft-delete

CREATE OR REPLACE VIEW main.finance.credit_customers AS
SELECT CAST(c.id AS STRING) AS customer_id,
       COALESCE(c.companyname, c.entityid) AS customer_name,
       c.creditlimit AS credit_limit,
       term.daysuntilnetdue AS payment_terms_days,
       cat.name AS industry
FROM netsuite.customer c
LEFT JOIN netsuite.term term ON term.id = c.terms
LEFT JOIN netsuite.customercategory cat ON cat.id = c.category
WHERE c.isinactive = 'F';
```

The view only has to provide the columns below. The engine also accepts `amount_paid` instead of
`amount_remaining`.

| Column | Type | Notes |
|---|---|---|
| `invoice_id`, `customer_id` | string | |
| `invoice_date`, `due_date` | date | |
| `amount` | decimal | base currency |
| `amount_remaining` | decimal | open balance today |
| `paid_date` | date | last payment applied; null if unpaid |
| `disputed` | boolean | optional |

---

## Running on a schedule without Databricks

Any scheduler that can run Python works: cron on a VM, Azure Automation, or GitHub Actions with
repository secrets. Map the secrets to the environment variables above and run
`credit-score run --source netsuite --out out/`. Then publish `out/dashboard.html` and the CSVs
wherever the finance team picks them up, such as SharePoint or email.
