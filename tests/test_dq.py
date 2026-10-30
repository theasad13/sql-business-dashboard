"""Data-quality checks: clean data passes, each planted bad row is caught by its own check."""
import pytest

from sqldash import db, generate, kpis
from tests.conftest import make_tiny


def failing(conn):
    return {d["check_name"]: d["failing_rows"] for d in kpis.dq_summary(conn) if d["failing_rows"]}


def test_clean_fixture_passes_every_check(tiny):
    assert failing(tiny) == {}
    assert len(kpis.dq_summary(tiny)) == len(kpis.DQ_CHECKS)


BAD_ROWS = {
    "order_without_items": "INSERT INTO orders VALUES (300, 1, '2025-03-01', '2025-03-31', 'Completed', 'Web');",
    "orphan_order_customer": """INSERT INTO orders VALUES (301, 77, '2025-03-01', '2025-03-31', 'Completed', 'Web');
                                INSERT INTO order_items VALUES (30, 301, 1, 1, 10.00, 0);""",
    "orphan_item_product": "INSERT INTO order_items VALUES (31, 101, 55, 1, 10.00, 0);",
    "bad_quantity_or_price": "INSERT INTO order_items VALUES (32, 101, 1, 1, 10.00, 150);",
    "due_before_order": """INSERT INTO orders VALUES (302, 1, '2025-03-10', '2025-03-01', 'Completed', 'Web');
                           INSERT INTO order_items VALUES (33, 302, 1, 1, 10.00, 0);""",
    "orphan_payment": "INSERT INTO payments VALUES (40, 9999, '2025-03-01', 5.00, 'Card');",
    "payment_before_order": "INSERT INTO payments VALUES (41, 105, '2025-03-01', 5.00, 'Card');",
    "payment_on_cancelled_order": "INSERT INTO payments VALUES (42, 106, '2025-03-12', 10.00, 'Card');",
    "overpaid_invoice": "INSERT INTO payments VALUES (43, 104, '2025-03-21', 40.00, 'Card');",
    "duplicate_customer_email": "INSERT INTO customers VALUES (9, 'Alpha Again', 'ALPHA@example.com', 'Retail Store', 1, '2025-03-01');",
    "missing_customer_region": "INSERT INTO customers VALUES (10, 'Lost Co', 'lost@example.com', 'Retail Store', 7, '2025-03-01');",
    "missing_email": "INSERT INTO customers VALUES (11, 'Quiet Co', '', 'Retail Store', 1, '2025-03-01');",
}


def test_every_check_has_a_planted_case():
    assert set(BAD_ROWS) == set(kpis.DQ_CHECKS)


@pytest.mark.parametrize("check", sorted(BAD_ROWS))
def test_check_catches_its_planted_row(check):
    conn = make_tiny(BAD_ROWS[check])
    assert failing(conn) == {check: 1}


def test_issue_rows_point_at_the_bad_record():
    conn = make_tiny(BAD_ROWS["orphan_payment"])
    issue = kpis.dq_issues(conn)[0]
    assert (issue["table_name"], issue["record_id"], issue["severity"]) == ("payments", 40, "error")


def test_generated_data_has_exactly_the_planted_issues():
    conn = db.connect()
    db.create_schema(conn)
    db.load_dataset(conn, generate.generate(seed=42))
    db.install_views(conn)
    assert failing(conn) == generate.PLANTED


def test_generated_data_without_planting_is_clean():
    conn = db.connect()
    db.create_schema(conn)
    db.load_dataset(conn, generate.generate(seed=42, plant_issues=False))
    db.install_views(conn)
    assert failing(conn) == {}
