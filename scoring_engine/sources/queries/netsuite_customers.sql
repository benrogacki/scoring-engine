-- Customer master for credit scoring: credit limit, terms and segment.
SELECT
    c.id                        AS customer_id,
    NVL(c.companyname, c.entityid) AS customer_name,
    c.creditlimit               AS credit_limit,
    term.daysuntilnetdue        AS payment_terms_days,
    BUILTIN.DF(c.category)      AS industry
FROM customer c
LEFT JOIN term ON term.id = c.terms
WHERE c.isinactive = 'F'
ORDER BY c.id
