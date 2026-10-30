"""The dashboard's in-browser numbers must equal the SQL views (checked by running core.js in Node)."""
import json
import re
import shutil
import subprocess

import pytest

from sqldash import dashboard, db, generate, kpis
from sqldash.dashboard import ASSETS

NODE = shutil.which("node")


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    conn = db.build(tmp_path_factory.mktemp("db") / "sample.db", generate.generate(seed=42))
    yield conn
    conn.close()


def run_core(payload: dict, filters: list[dict], tmp_path) -> list[dict]:
    data_file = tmp_path / "payload.json"
    data_file.write_text(json.dumps({"data": payload, "filters": filters}), encoding="utf-8")
    script = (
        f"const core = require({json.dumps(str(ASSETS / 'core.js'))});"
        f"const input = JSON.parse(require('fs').readFileSync({json.dumps(str(data_file))}, 'utf8'));"
        "const out = input.filters.map((f) => { const v = core.computeView(input.data, f);"
        " return {headline: v.headline, monthly: v.monthly, regions: v.regions, aging: v.aging,"
        " cohorts: v.cohorts, products: v.products, n_orders: v.orders.length, n_invoices: v.invoices.length}; });"
        "process.stdout.write(JSON.stringify(out));"
    )
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True, timeout=60)
    return json.loads(done.stdout)


def close(a, b, tol=0.011):
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(close(a[k], b[k], tol) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(close(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and abs(a - b) <= tol
    return a == b


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_unfiltered_dashboard_equals_sql_views(sample, tmp_path):
    view = run_core(dashboard.build_payload(sample), [{}], tmp_path)[0]
    assert close(view["headline"], kpis.headline(sample))
    assert close(view["monthly"], kpis.monthly(sample))
    assert close(view["aging"], kpis.aging(sample))
    assert close(view["cohorts"], kpis.cohorts(sample))
    assert close(view["regions"], kpis.regions(sample))
    sql_products = [{k: p[k] for k in ("product_name", "category", "units", "revenue", "gross_margin")}
                    for p in kpis.products(sample)]
    assert close(view["products"], sql_products)


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_filtered_dashboard_equals_filtered_sql(sample, tmp_path):
    payload = dashboard.build_payload(sample)
    east, corp = payload["regions"].index("East"), payload["segments"].index("Corporate")
    office = payload["categories"].index("Office")
    q2 = (payload["months"].index("2025-04"), payload["months"].index("2025-06"))
    views = run_core(payload, [
        {"region": east, "segment": corp},
        {"from": q2[0], "to": q2[1]},
        {"category": office},
    ], tmp_path)

    sql = db.rows(sample, """SELECT COUNT(*) AS orders, COUNT(DISTINCT customer_id) AS customers,
                                    ROUND(SUM(order_revenue), 2) AS revenue FROM v_orders
                             WHERE status = 'Completed' AND region_name = 'East' AND segment = 'Corporate'""")[0]
    ar = db.rows(sample, """SELECT ROUND(SUM(outstanding), 2) AS ar FROM v_open_invoices
                            WHERE region_name = 'East' AND segment = 'Corporate'""")[0]
    h = views[0]["headline"]
    assert (h["orders"], h["active_customers"]) == (sql["orders"], sql["customers"])
    assert close(h["revenue"], sql["revenue"]) and close(h["ar_outstanding"], ar["ar"])

    sql = db.rows(sample, """SELECT COUNT(*) AS orders, ROUND(SUM(order_revenue), 2) AS revenue FROM v_orders
                             WHERE status = 'Completed' AND month_key BETWEEN '2025-04' AND '2025-06'""")[0]
    h = views[1]["headline"]
    assert h["orders"] == sql["orders"] and close(h["revenue"], sql["revenue"])
    assert [m["month_key"] for m in views[1]["monthly"]] == ["2025-04", "2025-05", "2025-06"]

    sql = db.rows(sample, """SELECT COUNT(DISTINCT l.order_id) AS orders, ROUND(SUM(l.line_revenue), 2) AS revenue
                             FROM v_order_lines l JOIN orders o ON o.order_id = l.order_id
                             WHERE o.status = 'Completed' AND l.category = 'Office'""")[0]
    h = views[2]["headline"]
    assert h["orders"] == sql["orders"] and close(h["revenue"], sql["revenue"])
    assert {p["category"] for p in views[2]["products"]} == {"Office"}


def test_html_is_self_contained(sample, tmp_path):
    page = dashboard.write(sample, tmp_path / "d.html").read_text(encoding="utf-8")
    assert not re.search(r"__[A-Z_]+__|/\*__", page), "unfilled template placeholder"
    assert "<script src" not in page and "<link" not in page          # works offline
    assert "CREATE VIEW kpi_monthly_revenue AS" in page                # SQL shown under the chart
    assert "2025-12-31" in page
