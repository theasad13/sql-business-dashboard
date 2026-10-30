"""Write a single self-contained HTML dashboard (no server, no internet needed)."""
from __future__ import annotations

import html
import json
import sqlite3
from datetime import date
from pathlib import Path

from . import kpis
from .db import rows, view_sql

ASSETS = Path(__file__).resolve().parent / "assets"
SQL_PANELS = ("kpi_monthly_revenue", "kpi_region_sales", "kpi_product_sales", "v_open_invoices", "kpi_ar_aging",
              "kpi_cohort_retention", "dq_issues")


def _month_keys(conn: sqlite3.Connection) -> list[str]:
    """Every calendar month from the first order to the report date."""
    first = conn.execute("SELECT MIN(order_date) FROM orders").fetchone()[0]
    end = date.fromisoformat(kpis.report_date(conn))
    y, m = int(first[:4]), int(first[5:7])
    out = []
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def build_payload(conn: sqlite3.Connection) -> dict:
    """Compact fact arrays the dashboard filters in the browser. All come from the SQL views."""
    months = _month_keys(conn)
    m_idx = {k: i for i, k in enumerate(months)}

    orders = rows(conn, """SELECT order_id, order_date, month_key, customer_id, region_name, segment,
                                  order_revenue, order_cost
                           FROM v_orders WHERE status = 'Completed' ORDER BY order_date, order_id""")
    lines = rows(conn, """SELECT l.order_id, l.product_name, l.category, l.quantity, l.line_revenue, l.line_cost
                          FROM v_order_lines l JOIN orders o ON o.order_id = l.order_id
                          WHERE o.status = 'Completed' ORDER BY l.order_item_id""")
    payments = rows(conn, """SELECT strftime('%Y-%m', p.paid_on) AS month_key,
                                    COALESCE(o.region_name, 'Unknown') AS region_name,
                                    COALESCE(o.segment, 'Unknown') AS segment, p.amount
                             FROM payments p LEFT JOIN v_orders o ON o.order_id = p.order_id
                             ORDER BY p.payment_id""")
    invoices = rows(conn, """SELECT order_id, customer_id, region_name, segment, due_date, outstanding, days_past_due
                             FROM v_open_invoices ORDER BY due_date, order_id""")

    regions = sorted({o["region_name"] for o in orders} | {i["region_name"] for i in invoices}, key=_unknown_last)
    segments = sorted({o["segment"] for o in orders} | {i["segment"] for i in invoices}, key=_unknown_last)
    categories = sorted({line["category"] for line in lines}, key=_unknown_last)
    products = sorted({(line["product_name"], line["category"]) for line in lines})
    r_idx = {k: i for i, k in enumerate(regions)}
    s_idx = {k: i for i, k in enumerate(segments)}
    c_idx = {k: i for i, k in enumerate(categories)}
    p_idx = {k: i for i, k in enumerate(products)}
    o_pos = {o["order_id"]: i for i, o in enumerate(orders)}

    return {
        "months": months,
        "regions": regions,
        "segments": segments,
        "categories": categories,
        "products": [[name, c_idx[cat]] for name, cat in products],
        "orders": [[o["order_id"], o["order_date"], m_idx[o["month_key"]], o["customer_id"], r_idx[o["region_name"]],
                    s_idx[o["segment"]], round(o["order_revenue"], 2), round(o["order_cost"], 2)] for o in orders],
        "lines": [[o_pos[li["order_id"]], p_idx[(li["product_name"], li["category"])], li["quantity"],
                   round(li["line_revenue"], 2), round(li["line_cost"], 2)] for li in lines],
        # payments outside the order months, or for orders the filters can't place, still count when unfiltered
        "payments": [[m_idx[p["month_key"]], r_idx.get(p["region_name"], -2), s_idx.get(p["segment"], -2),
                      round(p["amount"], 2)] for p in payments if p["month_key"] in m_idx],
        "invoices": [[i["order_id"], i["customer_id"], r_idx[i["region_name"]], s_idx[i["segment"]], i["due_date"],
                      round(i["outstanding"], 2), i["days_past_due"]] for i in invoices],
    }


def _unknown_last(name: str) -> tuple:
    return (name == "Unknown", name)


def _script_json(value) -> str:
    return json.dumps(value, separators=(",", ":")).replace("</", "<\\/")


def render(conn: sqlite3.Connection) -> str:
    page = (ASSETS / "template.html").read_text(encoding="utf-8")
    parts = {
        "/*__CSS__*/": (ASSETS / "style.css").read_text(encoding="utf-8"),
        "/*__CORE_JS__*/": (ASSETS / "core.js").read_text(encoding="utf-8"),
        "/*__UI_JS__*/": (ASSETS / "ui.js").read_text(encoding="utf-8"),
        "__DATA__": _script_json(build_payload(conn)),
        "__DQ__": _script_json(kpis.dq_summary(conn)),
        "__REPORT_DATE__": kpis.report_date(conn),
    }
    for name in SQL_PANELS:
        parts[f"__SQL_{name}__"] = html.escape(view_sql(name))
    for key, value in parts.items():
        page = page.replace(key, value)
    return page


def write(conn: sqlite3.Connection, out: str | Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(conn), encoding="utf-8")
    return out
