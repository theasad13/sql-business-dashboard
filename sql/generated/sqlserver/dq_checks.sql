-- GENERATED from sql/dq_checks.sql by `python -m sqldash export-sql`. Do not edit by hand.
-- Data-quality checks. Each SELECT returns the offending rows for one rule, so
-- a failing check tells you exactly which record to fix, not just a count.
-- Needs views.sql first (overpaid_invoice uses v_invoice_balances).

DROP VIEW IF EXISTS dq_issues;
GO

-- view: dq_issues
CREATE VIEW dq_issues AS
SELECT 'order_without_items' AS check_name, 'error' AS severity, 'orders' AS table_name,
       o.order_id AS record_id, 'Order has no line items' AS detail
FROM orders o
WHERE NOT EXISTS (SELECT 1 FROM order_items i WHERE i.order_id = o.order_id)

UNION ALL
SELECT 'orphan_order_customer', 'error', 'orders', o.order_id, 'customer_id not found in customers'
FROM orders o
LEFT JOIN customers c ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL

UNION ALL
SELECT 'orphan_item_product', 'error', 'order_items', i.order_item_id, 'product_id not found in products'
FROM order_items i
LEFT JOIN products p ON p.product_id = i.product_id
WHERE p.product_id IS NULL

UNION ALL
SELECT 'bad_quantity_or_price', 'error', 'order_items', i.order_item_id,
       'quantity <= 0, negative price or discount outside 0-100'
FROM order_items i
WHERE i.quantity <= 0 OR i.unit_price < 0 OR i.discount_pct < 0 OR i.discount_pct > 100

UNION ALL
SELECT 'due_before_order', 'error', 'orders', o.order_id, 'due_date is before order_date'
FROM orders o
WHERE o.due_date < o.order_date

UNION ALL
SELECT 'orphan_payment', 'error', 'payments', p.payment_id, 'order_id not found in orders'
FROM payments p
LEFT JOIN orders o ON o.order_id = p.order_id
WHERE o.order_id IS NULL

UNION ALL
SELECT 'payment_before_order', 'error', 'payments', p.payment_id, 'paid_on is before the order_date'
FROM payments p
JOIN orders o ON o.order_id = p.order_id
WHERE p.paid_on < o.order_date

UNION ALL
SELECT 'payment_on_cancelled_order', 'warning', 'payments', p.payment_id, 'payment recorded against a cancelled order'
FROM payments p
JOIN orders o ON o.order_id = p.order_id
WHERE o.status = 'Cancelled'

UNION ALL
SELECT 'overpaid_invoice', 'warning', 'orders', b.order_id, 'payments exceed the invoice amount'
FROM v_invoice_balances b
WHERE b.outstanding < -0.005

UNION ALL
SELECT 'duplicate_customer_email', 'warning', 'customers', c.customer_id, 'email already used by an older customer record'
FROM customers c
WHERE EXISTS (
    SELECT 1 FROM customers c2
    WHERE LOWER(c2.email) = LOWER(c.email) AND c2.customer_id < c.customer_id
)

UNION ALL
SELECT 'missing_customer_region', 'warning', 'customers', c.customer_id, 'region_id is empty or unknown'
FROM customers c
LEFT JOIN regions r ON r.region_id = c.region_id
WHERE r.region_id IS NULL

UNION ALL
SELECT 'missing_email', 'warning', 'customers', c.customer_id, 'email is empty'
FROM customers c
WHERE c.email IS NULL OR c.email = '';
GO
