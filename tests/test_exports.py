"""Power BI star-schema CSVs, loading a client's own CSVs, and the CLI."""
import csv

from sqldash import db, kpis, powerbi
from sqldash.__main__ import main
from tests.conftest import make_tiny


def read(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_powerbi_star_schema_totals_match_sql(tiny, tmp_path):
    counts = powerbi.export(tiny, tmp_path)
    assert set(counts) == {"dim_date.csv", "dim_customer.csv", "dim_product.csv",
                           "fact_sales.csv", "fact_payments.csv", "fact_open_invoices.csv"}
    sales = read(tmp_path / "fact_sales.csv")
    assert round(sum(float(r["revenue"]) for r in sales), 2) == kpis.headline(tiny)["revenue"] == 530.0
    assert len({r["order_id"] for r in sales}) == 7
    open_inv = read(tmp_path / "fact_open_invoices.csv")
    assert round(sum(float(r["outstanding"]) for r in open_inv), 2) == 300.0
    # every fact key exists in its dimension (relationships will not break in Power BI)
    customers = {r["customer_key"] for r in read(tmp_path / "dim_customer.csv")}
    products = {r["product_key"] for r in read(tmp_path / "dim_product.csv")}
    dates = {r["date"] for r in read(tmp_path / "dim_date.csv")}
    assert {r["customer_key"] for r in sales} <= customers
    assert {r["product_key"] for r in sales} <= products
    assert {r["order_date"] for r in sales} <= dates
    assert {r["due_date"] for r in open_inv} <= dates


def test_orphans_map_to_unknown_member(tmp_path):
    conn = make_tiny("""
        INSERT INTO orders VALUES (200, 999, '2025-03-15', '2025-04-14', 'Completed', 'Web');
        INSERT INTO order_items VALUES (20, 200, 77, 4, 10.00, 0);
    """)
    powerbi.export(conn, tmp_path)
    row = [r for r in read(tmp_path / "fact_sales.csv") if r["order_id"] == "200"][0]
    assert (row["customer_key"], row["product_key"]) == ("-1", "-1")


def test_build_from_client_csvs_gives_same_kpis(tiny, tmp_path):
    src = tmp_path / "csv"
    src.mkdir()
    for table in db.TABLES[:-1]:
        cur = tiny.execute(f"SELECT * FROM {table}")
        with (src / f"{table}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow([c[0] for c in cur.description])
            w.writerows(cur.fetchall())
    conn = db.build_from_csv(tmp_path / "client.db", src, "2025-03-31")
    assert kpis.headline(conn) == kpis.headline(tiny)
    assert kpis.aging(conn) == kpis.aging(tiny)


def test_cli_demo_writes_everything(tmp_path, capsys):
    out = tmp_path / "dash.html"
    assert main(["demo", "--db", str(tmp_path / "x.db"), "--out", str(out), "--no-open"]) == 0
    text = capsys.readouterr().out
    assert "Revenue" in text and "Data-quality checks" in text
    assert out.exists() and out.stat().st_size > 50_000
