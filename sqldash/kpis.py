"""Run the KPI views and data-quality checks; return plain Python data."""
from __future__ import annotations

import sqlite3

from .db import rows

# check name -> (severity, what it means), in the order the report lists them.
DQ_CHECKS = {
    "order_without_items": ("error", "Order has no line items"),
    "orphan_order_customer": ("error", "Order points to a customer that does not exist"),
    "orphan_item_product": ("error", "Order line points to a product that does not exist"),
    "bad_quantity_or_price": ("error", "Quantity <= 0, negative price, or discount outside 0-100%"),
    "due_before_order": ("error", "Invoice due date is before the order date"),
    "orphan_payment": ("error", "Payment points to an order that does not exist"),
    "payment_before_order": ("error", "Payment dated before its order"),
    "payment_on_cancelled_order": ("warning", "Payment recorded against a cancelled order"),
    "overpaid_invoice": ("warning", "Payments exceed the invoice amount"),
    "duplicate_customer_email": ("warning", "Customer email already used by an older record"),
    "missing_customer_region": ("warning", "Customer has no valid region"),
    "missing_email": ("warning", "Customer has no email"),
}


def headline(conn: sqlite3.Connection) -> dict:
    return rows(conn, "SELECT * FROM kpi_headline")[0]


def monthly(conn: sqlite3.Connection) -> list[dict]:
    return rows(conn, "SELECT * FROM kpi_monthly_revenue ORDER BY month_key")


def aging(conn: sqlite3.Connection) -> list[dict]:
    return rows(conn, "SELECT * FROM kpi_ar_aging ORDER BY bucket_order")


def cohorts(conn: sqlite3.Connection) -> list[dict]:
    return rows(conn, "SELECT * FROM kpi_cohort_retention ORDER BY cohort_month, months_since_first")


def products(conn: sqlite3.Connection, limit: int | None = None) -> list[dict]:
    sql = "SELECT * FROM kpi_product_sales ORDER BY revenue_rank, product_name"
    return rows(conn, sql + (f" LIMIT {int(limit)}" if limit else ""))


def regions(conn: sqlite3.Connection) -> list[dict]:
    return rows(conn, "SELECT * FROM kpi_region_sales ORDER BY revenue DESC")


def report_date(conn: sqlite3.Connection) -> str:
    return conn.execute("SELECT report_date FROM report_params").fetchone()[0]


def dq_issues(conn: sqlite3.Connection) -> list[dict]:
    return rows(conn, "SELECT * FROM dq_issues ORDER BY check_name, record_id")


def dq_summary(conn: sqlite3.Connection) -> list[dict]:
    """Every check, including the ones that pass, with its failing-row count."""
    counts = {r["check_name"]: r["n"] for r in rows(
        conn, "SELECT check_name, COUNT(*) AS n FROM dq_issues GROUP BY check_name")}
    return [{"check_name": name, "severity": severity, "description": meaning, "failing_rows": counts.get(name, 0)}
            for name, (severity, meaning) in DQ_CHECKS.items()]
