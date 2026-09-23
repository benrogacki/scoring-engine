-- Customer invoices for credit scoring, in the engine's canonical columns.
-- {lookback_months} is filled in by the engine (default 15).
--
-- Adjust to your account before relying on it:
--   * Amounts are converted to base currency with the invoice exchange rate.
--   * paid_date is the latest payment / credit applied to the invoice.
--   * `disputed` needs a custom body field; replace custbody_disputed with yours
--     or change the line to: 'F' AS disputed
--   * Add a subsidiary filter (t.subsidiary = ...) if you score one entity.
SELECT
    t.id                                                AS invoice_id,
    t.tranid                                            AS invoice_number,
    t.entity                                            AS customer_id,
    TO_CHAR(t.trandate, 'YYYY-MM-DD')                   AS invoice_date,
    TO_CHAR(NVL(t.duedate, t.trandate), 'YYYY-MM-DD')   AS due_date,
    t.foreigntotal * NVL(t.exchangerate, 1)             AS amount,
    NVL(t.foreignamountremaining, 0) * NVL(t.exchangerate, 1) AS amount_remaining,
    TO_CHAR(pay.last_payment_date, 'YYYY-MM-DD')        AS paid_date,
    t.custbody_disputed                                 AS disputed
FROM transaction t
LEFT JOIN (
    SELECT link.previousdoc AS invoice_id, MAX(nxt.trandate) AS last_payment_date
    FROM NextTransactionLink link
    JOIN transaction nxt ON nxt.id = link.nextdoc
    WHERE nxt.type IN ('CustPymt', 'CustCred', 'Journal')
    GROUP BY link.previousdoc
) pay ON pay.invoice_id = t.id
WHERE t.type = 'CustInvc'
  AND t.posting = 'T'
  AND t.voided = 'F'
  AND t.trandate >= ADD_MONTHS(TRUNC(SYSDATE), -{lookback_months})
ORDER BY t.id
