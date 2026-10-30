"""Each KPI view against numbers worked out by hand from tests/fixtures/tiny.sql."""
from sqldash import kpis


def test_headline(tiny):
    # Completed orders: 100,101,102,108,103,104,105 -> 7 orders, customers 1-4
    # Revenue 50+100+110+10+30+40+190 = 530; cost 30+60+87+6+18+30+150 = 381; margin 149
    # Open: 100 30.00 | 101 100.00 | 102 50.00 | 103 30.00 (April payment ignored) | 105 90.00 = 300.00
    # Overdue = all but 105 = 210.00 -> 70.0%
    assert kpis.headline(tiny) == {
        "orders": 7,
        "active_customers": 4,
        "revenue": 530.0,
        "gross_margin": 149.0,
        "gross_margin_pct": 28.1,       # 149 / 530
        "avg_order_value": 75.71,       # 530 / 7
        "ar_outstanding": 300.0,
        "ar_overdue": 210.0,
        "ar_overdue_pct": 70.0,
    }


def test_monthly_revenue(tiny):
    assert kpis.monthly(tiny) == [
        # Dec: order 100; no payments that month
        {"month_key": "2024-12", "orders": 1, "active_customers": 1, "revenue": 50.0, "gross_margin": 20.0,
         "avg_order_value": 50.0, "collections": 0.0},
        # Jan: 101,102,108 = 100+110+10; margin 40+23+4; payment 1 (20.00)
        {"month_key": "2025-01", "orders": 3, "active_customers": 3, "revenue": 220.0, "gross_margin": 67.0,
         "avg_order_value": 73.33, "collections": 20.0},
        # Feb: 103,104 = 30+40; margin 12+10; payment 6 (10.00)
        {"month_key": "2025-02", "orders": 2, "active_customers": 2, "revenue": 70.0, "gross_margin": 22.0,
         "avg_order_value": 35.0, "collections": 10.0},
        # Mar: 105 (106 cancelled); payments 2,3,5 = 60+40+100
        {"month_key": "2025-03", "orders": 1, "active_customers": 1, "revenue": 190.0, "gross_margin": 40.0,
         "avg_order_value": 190.0, "collections": 200.0},
    ]


def test_ar_aging(tiny):
    assert kpis.aging(tiny) == [
        {"bucket_order": 1, "aging_bucket": "Not yet due", "open_invoices": 1, "outstanding": 90.0, "pct_of_total": 30.0},
        {"bucket_order": 2, "aging_bucket": "1-30 days", "open_invoices": 1, "outstanding": 30.0, "pct_of_total": 10.0},
        {"bucket_order": 3, "aging_bucket": "31-60 days", "open_invoices": 1, "outstanding": 50.0, "pct_of_total": 16.7},
        {"bucket_order": 4, "aging_bucket": "61-90 days", "open_invoices": 1, "outstanding": 100.0, "pct_of_total": 33.3},
        {"bucket_order": 5, "aging_bucket": "90+ days", "open_invoices": 1, "outstanding": 30.0, "pct_of_total": 10.0},
    ]


def test_open_invoice_days_past_due(tiny):
    got = {r["order_id"]: r["days_past_due"] for r in tiny.execute("SELECT order_id, days_past_due FROM v_open_invoices")}
    assert got == {100: 91, 101: 65, 102: 39, 103: 14, 105: -19}


def test_cohort_retention(tiny):
    # First orders: cust 2 Dec-24; cust 1 and 4 Jan-25; cust 3 Feb-25 (its March order is cancelled)
    rows = [(r["cohort_month"], r["months_since_first"], r["cohort_size"], r["active_customers"], r["retention_pct"])
            for r in kpis.cohorts(tiny)]
    assert rows == [
        ("2024-12", 0, 1, 1, 100.0),
        ("2024-12", 1, 1, 1, 100.0),   # Jan order 102
        ("2024-12", 3, 1, 1, 100.0),   # Mar order 105
        ("2025-01", 0, 2, 2, 100.0),
        ("2025-01", 1, 2, 1, 50.0),    # only cust 1 came back (order 103)
        ("2025-02", 0, 1, 1, 100.0),
    ]


def test_product_sales(tiny):
    # Gadget: 90+40+190 = 320, cost 75+30+150; Widget: 50+100+20+10+30 = 210, cost 126 (cancelled 106 excluded)
    assert kpis.products(tiny) == [
        {"product_id": 2, "product_name": "Gadget", "category": "Cleaning", "units": 17, "revenue": 320.0,
         "gross_margin": 65.0, "revenue_rank": 1},
        {"product_id": 1, "product_name": "Widget", "category": "Office", "units": 21, "revenue": 210.0,
         "gross_margin": 84.0, "revenue_rank": 2},
    ]


def test_region_sales(tiny):
    # South = cust 2 + 4: 50+110+190+10 = 360; North = cust 1 + 3: 100+30+40 = 170
    assert kpis.regions(tiny) == [
        {"region_name": "South", "active_customers": 2, "orders": 4, "revenue": 360.0, "gross_margin": 87.0,
         "revenue_share_pct": 67.9},
        {"region_name": "North", "active_customers": 2, "orders": 3, "revenue": 170.0, "gross_margin": 62.0,
         "revenue_share_pct": 32.1},
    ]


def test_orphan_order_shows_as_unknown_region_not_lost():
    from tests.conftest import make_tiny
    conn = make_tiny("""
        INSERT INTO orders VALUES (200, 999, '2025-03-15', '2025-04-14', 'Completed', 'Web');
        INSERT INTO order_items VALUES (20, 200, 1, 4, 10.00, 0);
    """)
    regions = {r["region_name"]: r["revenue"] for r in kpis.regions(conn)}
    assert regions["Unknown"] == 40.0
    assert sum(regions.values()) == kpis.headline(conn)["revenue"] == 570.0
