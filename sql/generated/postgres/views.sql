-- GENERATED from sql/views.sql by `python -m sqldash export-sql`. Do not edit by hand.
-- KPI views. Written once in portable SQL with three small macros that
-- sqldash/dialects.py expands per database:
--   @MONTH(d)            -> 'YYYY-MM' text
--   @MONTH_INDEX(d)      -> year * 12 + month, for "months between" maths
--   @DAYS_BETWEEN(a, b)  -> whole days from a to b
-- Views never use ORDER BY (SQL Server forbids it); sort when you query them.

DROP VIEW IF EXISTS kpi_headline;
DROP VIEW IF EXISTS kpi_region_sales;
DROP VIEW IF EXISTS kpi_product_sales;
DROP VIEW IF EXISTS kpi_cohort_retention;
DROP VIEW IF EXISTS kpi_ar_aging;
DROP VIEW IF EXISTS v_open_invoices;
DROP VIEW IF EXISTS v_invoice_balances;
DROP VIEW IF EXISTS kpi_monthly_revenue;
DROP VIEW IF EXISTS v_orders;
DROP VIEW IF EXISTS v_order_lines;

-- view: v_order_lines
-- One row per invoice line, with revenue after discount and cost at standard cost.
CREATE VIEW v_order_lines AS
SELECT
    oi.order_item_id,
    oi.order_id,
    oi.product_id,
    COALESCE(p.product_name, 'Unknown') AS product_name,
    COALESCE(p.category, 'Unknown')     AS category,
    oi.quantity,
    ROUND(oi.quantity * oi.unit_price * (100 - oi.discount_pct) / 100.0, 2) AS line_revenue,
    ROUND(oi.quantity * COALESCE(p.unit_cost, 0), 2)                         AS line_cost
FROM order_items oi
LEFT JOIN products p ON p.product_id = oi.product_id;

-- view: v_orders
-- One row per order with its customer's segment and region. LEFT JOINs keep
-- orders whose customer is missing (they show as 'Unknown', never vanish).
CREATE VIEW v_orders AS
SELECT
    o.order_id,
    o.customer_id,
    o.order_date,
    o.due_date,
    o.status,
    o.channel,
    to_char(o.order_date, 'YYYY-MM')                AS month_key,
    COALESCE(c.segment, 'Unknown')      AS segment,
    COALESCE(r.region_name, 'Unknown')  AS region_name,
    COALESCE(t.order_revenue, 0)        AS order_revenue,
    COALESCE(t.order_cost, 0)           AS order_cost
FROM orders o
LEFT JOIN customers c ON c.customer_id = o.customer_id
LEFT JOIN regions r   ON r.region_id = c.region_id
LEFT JOIN (
    SELECT order_id, SUM(line_revenue) AS order_revenue, SUM(line_cost) AS order_cost
    FROM v_order_lines
    GROUP BY order_id
) t ON t.order_id = o.order_id;

-- view: kpi_monthly_revenue
-- Revenue trend: invoiced sales vs cash collected, per calendar month.
CREATE VIEW kpi_monthly_revenue AS
WITH sales AS (
    SELECT month_key,
           COUNT(*)                          AS orders,
           COUNT(DISTINCT customer_id)       AS active_customers,
           SUM(order_revenue)                AS revenue,
           SUM(order_revenue - order_cost)   AS gross_margin
    FROM v_orders
    WHERE status = 'Completed'
    GROUP BY month_key
), cash AS (
    SELECT to_char(paid_on, 'YYYY-MM') AS month_key, SUM(amount) AS collections
    FROM payments
    GROUP BY to_char(paid_on, 'YYYY-MM')
)
SELECT
    s.month_key,
    s.orders,
    s.active_customers,
    ROUND(s.revenue, 2)                          AS revenue,
    ROUND(s.gross_margin, 2)                     AS gross_margin,
    ROUND(s.revenue / NULLIF(s.orders, 0), 2)    AS avg_order_value,
    ROUND(COALESCE(c.collections, 0), 2)         AS collections
FROM sales s
LEFT JOIN cash c ON c.month_key = s.month_key;

-- view: v_invoice_balances
-- Every completed invoice with what was paid up to the report date.
CREATE VIEW v_invoice_balances AS
WITH paid AS (
    SELECT p.order_id, SUM(p.amount) AS paid_to_date
    FROM payments p
    CROSS JOIN report_params rp
    WHERE p.paid_on <= rp.report_date
    GROUP BY p.order_id
)
SELECT
    o.order_id,
    o.customer_id,
    o.region_name,
    o.segment,
    o.order_date,
    o.due_date,
    o.order_revenue                                AS invoice_amount,
    COALESCE(pd.paid_to_date, 0)                   AS paid_to_date,
    o.order_revenue - COALESCE(pd.paid_to_date, 0) AS outstanding,
    (CAST(rp.report_date AS DATE) - CAST(o.due_date AS DATE))      AS days_past_due
FROM v_orders o
CROSS JOIN report_params rp
LEFT JOIN paid pd ON pd.order_id = o.order_id
WHERE o.status = 'Completed'
  AND o.order_date <= rp.report_date;

-- view: v_open_invoices
-- Unpaid invoices with their aging bucket (days past due date).
CREATE VIEW v_open_invoices AS
SELECT
    b.*,
    CASE WHEN b.days_past_due <= 0  THEN 1
         WHEN b.days_past_due <= 30 THEN 2
         WHEN b.days_past_due <= 60 THEN 3
         WHEN b.days_past_due <= 90 THEN 4
         ELSE 5 END AS bucket_order,
    CASE WHEN b.days_past_due <= 0  THEN 'Not yet due'
         WHEN b.days_past_due <= 30 THEN '1-30 days'
         WHEN b.days_past_due <= 60 THEN '31-60 days'
         WHEN b.days_past_due <= 90 THEN '61-90 days'
         ELSE '90+ days' END AS aging_bucket
FROM v_invoice_balances b
WHERE b.outstanding > 0.005;

-- view: kpi_ar_aging
-- Receivables aging: how much customers owe, by how late it is.
CREATE VIEW kpi_ar_aging AS
SELECT
    bucket_order,
    aging_bucket,
    COUNT(*)                  AS open_invoices,
    ROUND(SUM(outstanding), 2) AS outstanding,
    ROUND(100.0 * SUM(outstanding) / SUM(SUM(outstanding)) OVER (), 1) AS pct_of_total
FROM v_open_invoices
GROUP BY bucket_order, aging_bucket;

-- view: kpi_cohort_retention
-- Customers grouped by the month of their first order; what share of each
-- group ordered again N months later.
CREATE VIEW kpi_cohort_retention AS
WITH completed AS (
    SELECT customer_id, order_date FROM v_orders WHERE status = 'Completed'
), first_order AS (
    SELECT customer_id, MIN(order_date) AS first_date
    FROM completed
    GROUP BY customer_id
), activity AS (
    SELECT DISTINCT
        f.customer_id,
        to_char(f.first_date, 'YYYY-MM') AS cohort_month,
        (CAST(EXTRACT(YEAR FROM c.order_date) AS INTEGER) * 12 + CAST(EXTRACT(MONTH FROM c.order_date) AS INTEGER)) - (CAST(EXTRACT(YEAR FROM f.first_date) AS INTEGER) * 12 + CAST(EXTRACT(MONTH FROM f.first_date) AS INTEGER)) AS months_since_first
    FROM first_order f
    JOIN completed c ON c.customer_id = f.customer_id
), sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_size
    FROM activity
    WHERE months_since_first = 0
    GROUP BY cohort_month
)
SELECT
    a.cohort_month,
    a.months_since_first,
    s.cohort_size,
    COUNT(*) AS active_customers,
    ROUND(100.0 * COUNT(*) / s.cohort_size, 1) AS retention_pct
FROM activity a
JOIN sizes s ON s.cohort_month = a.cohort_month
GROUP BY a.cohort_month, a.months_since_first, s.cohort_size;

-- view: kpi_product_sales
-- Units, revenue and margin per product, ranked by revenue.
CREATE VIEW kpi_product_sales AS
SELECT
    l.product_id,
    l.product_name,
    l.category,
    SUM(l.quantity)                           AS units,
    ROUND(SUM(l.line_revenue), 2)             AS revenue,
    ROUND(SUM(l.line_revenue - l.line_cost), 2) AS gross_margin,
    RANK() OVER (ORDER BY SUM(l.line_revenue) DESC) AS revenue_rank
FROM v_order_lines l
JOIN orders o ON o.order_id = l.order_id
WHERE o.status = 'Completed'
GROUP BY l.product_id, l.product_name, l.category;

-- view: kpi_region_sales
-- Sales by region with each region's share of total revenue.
CREATE VIEW kpi_region_sales AS
SELECT
    region_name,
    COUNT(DISTINCT customer_id)               AS active_customers,
    COUNT(*)                                  AS orders,
    ROUND(SUM(order_revenue), 2)              AS revenue,
    ROUND(SUM(order_revenue - order_cost), 2) AS gross_margin,
    ROUND(100.0 * SUM(order_revenue) / SUM(SUM(order_revenue)) OVER (), 1) AS revenue_share_pct
FROM v_orders
WHERE status = 'Completed'
GROUP BY region_name;

-- view: kpi_headline
-- One row of headline numbers for the KPI tiles.
CREATE VIEW kpi_headline AS
WITH s AS (
    SELECT COUNT(*)                        AS orders,
           COUNT(DISTINCT customer_id)     AS active_customers,
           SUM(order_revenue)              AS revenue,
           SUM(order_revenue - order_cost) AS gross_margin
    FROM v_orders
    WHERE status = 'Completed'
), ar AS (
    SELECT SUM(outstanding)                                         AS ar_outstanding,
           SUM(CASE WHEN days_past_due > 0 THEN outstanding ELSE 0 END) AS ar_overdue
    FROM v_open_invoices
)
SELECT
    s.orders,
    s.active_customers,
    ROUND(s.revenue, 2)                                       AS revenue,
    ROUND(s.gross_margin, 2)                                  AS gross_margin,
    ROUND(100.0 * s.gross_margin / NULLIF(s.revenue, 0), 1)   AS gross_margin_pct,
    ROUND(s.revenue / NULLIF(s.orders, 0), 2)                 AS avg_order_value,
    ROUND(COALESCE(ar.ar_outstanding, 0), 2)                  AS ar_outstanding,
    ROUND(COALESCE(ar.ar_overdue, 0), 2)                      AS ar_overdue,
    ROUND(100.0 * ar.ar_overdue / NULLIF(ar.ar_outstanding, 0), 1) AS ar_overdue_pct
FROM s
CROSS JOIN ar;
