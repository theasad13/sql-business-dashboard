"""Star-schema CSV export for Power BI (or Excel / Tableau / Looker Studio).

dim_date, dim_customer, dim_product + fact_sales, fact_payments, fact_open_invoices.
Rows whose customer or product is missing get key -1 ("Unknown") so totals never drop rows.
"""
from __future__ import annotations

import csv
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from .db import rows

QUERIES = {
    "dim_customer": """
        SELECT -1 AS customer_key, 'Unknown' AS customer_name, 'Unknown' AS segment, 'Unknown' AS region, NULL AS created_on
        UNION ALL
        SELECT c.customer_id, c.customer_name, c.segment, COALESCE(r.region_name, 'Unknown'), c.created_on
        FROM customers c LEFT JOIN regions r ON r.region_id = c.region_id
        ORDER BY customer_key""",
    "dim_product": """
        SELECT -1 AS product_key, 'Unknown' AS product_name, 'Unknown' AS category, NULL AS unit_cost, NULL AS list_price
        UNION ALL
        SELECT product_id, product_name, category, unit_cost, list_price FROM products
        ORDER BY product_key""",
    "fact_sales": """
        SELECT l.order_item_id, l.order_id, o.order_date, o.channel,
               CASE WHEN c.customer_id IS NULL THEN -1 ELSE o.customer_id END AS customer_key,
               CASE WHEN p.product_id IS NULL THEN -1 ELSE l.product_id END AS product_key,
               l.quantity, l.line_revenue AS revenue, l.line_cost AS cost,
               ROUND(l.line_revenue - l.line_cost, 2) AS gross_margin
        FROM v_order_lines l
        JOIN orders o ON o.order_id = l.order_id
        LEFT JOIN customers c ON c.customer_id = o.customer_id
        LEFT JOIN products p ON p.product_id = l.product_id
        WHERE o.status = 'Completed'
        ORDER BY l.order_item_id""",
    "fact_payments": """
        SELECT p.payment_id, p.order_id, p.paid_on, p.method, p.amount,
               CASE WHEN c.customer_id IS NULL THEN -1 ELSE o.customer_id END AS customer_key
        FROM payments p
        LEFT JOIN orders o ON o.order_id = p.order_id
        LEFT JOIN customers c ON c.customer_id = o.customer_id
        ORDER BY p.payment_id""",
    "fact_open_invoices": """
        SELECT i.order_id, i.order_date, i.due_date,
               CASE WHEN c.customer_id IS NULL THEN -1 ELSE i.customer_id END AS customer_key,
               ROUND(i.invoice_amount, 2) AS invoice_amount, ROUND(i.paid_to_date, 2) AS paid_to_date,
               ROUND(i.outstanding, 2) AS outstanding, i.days_past_due, i.aging_bucket, i.bucket_order
        FROM v_open_invoices i
        LEFT JOIN customers c ON c.customer_id = i.customer_id
        ORDER BY i.order_id""",
}


def _dim_date(conn: sqlite3.Connection) -> list[dict]:
    lo, hi = conn.execute("""SELECT MIN(d), MAX(d) FROM (
        SELECT order_date AS d FROM orders UNION ALL SELECT due_date FROM orders
        UNION ALL SELECT paid_on FROM payments UNION ALL SELECT report_date FROM report_params)""").fetchone()
    start = date(int(lo[:4]), 1, 1)
    end = date(int(hi[:4]), 12, 31)
    out, d = [], start
    while d <= end:
        out.append({
            "date": d.isoformat(),
            "year": d.year,
            "quarter": f"Q{(d.month - 1) // 3 + 1}",
            "month_num": d.month,
            "month_name": d.strftime("%b"),
            "month_key": d.strftime("%Y-%m"),
            "weekday": d.strftime("%a"),
        })
        d += timedelta(days=1)
    return out


def export(conn: sqlite3.Connection, out_dir: str | Path) -> dict[str, int]:
    """Write the CSVs; return {file: row count}."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = {"dim_date": _dim_date(conn)}
    tables.update({name: rows(conn, sql) for name, sql in QUERIES.items()})
    counts = {}
    for name, data in tables.items():
        with (out_dir / f"{name}.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(data[0]))
            writer.writeheader()
            for r in data:
                writer.writerow({k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()})
        counts[f"{name}.csv"] = len(data)
    return counts
