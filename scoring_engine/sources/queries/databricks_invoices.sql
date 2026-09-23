-- Default Databricks query: reads a curated view with the engine's columns.
-- See docs/integrations.md for an example view over NetSuite data synced to Databricks.
SELECT invoice_id, customer_id, invoice_date, due_date, amount,
       amount_remaining, paid_date, disputed
FROM {invoices_table}
WHERE invoice_date >= add_months(current_date(), -{lookback_months})
