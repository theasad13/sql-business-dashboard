"""Macro expansion for SQLite / SQL Server / PostgreSQL, and the committed generated scripts."""
import pytest

from sqldash import db
from sqldash.__main__ import export_sql
from sqldash.dialects import DIALECTS, render, split_statements


def test_macros_expand_per_dialect():
    sql = "SELECT @MONTH(o.order_date), @DAYS_BETWEEN(o.due_date, COALESCE(x, y)) FROM o;"
    assert render(sql, "sqlite") == ("SELECT strftime('%Y-%m', o.order_date), "
                                     "CAST(julianday(COALESCE(x, y)) - julianday(o.due_date) AS INTEGER) FROM o;")
    assert render(sql, "sqlserver") == ("SELECT CONVERT(CHAR(7), o.order_date, 126), "
                                        "DATEDIFF(day, o.due_date, COALESCE(x, y)) FROM o;\nGO\n")
    assert render(sql, "postgres") == ("SELECT to_char(o.order_date, 'YYYY-MM'), "
                                       "(CAST(COALESCE(x, y) AS DATE) - CAST(o.due_date AS DATE)) FROM o;")


def test_comments_and_bad_input():
    assert render("-- @MONTH(d) stays\nSELECT 1;", "postgres") == "-- @MONTH(d) stays\nSELECT 1;"
    with pytest.raises(ValueError):
        render("SELECT @NOPE(a);", "sqlite")
    with pytest.raises(ValueError):
        render("SELECT 1;", "oracle")


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("name", db.SQL_FILES)
def test_no_macros_left_outside_comments(dialect, name):
    for stmt in split_statements(db.read_sql(name, dialect)):
        code = "\n".join(line for line in stmt.splitlines() if not line.strip().startswith("--"))
        assert "@" not in code


def test_sqlserver_views_are_in_separate_batches():
    text = db.read_sql("views.sql", "sqlserver")
    assert text.count("CREATE VIEW") == text.count(";\nGO\n") - text.count("DROP VIEW")
    assert "ORDER BY" not in text.split("CREATE VIEW", 1)[1].replace("OVER (ORDER BY", "")


def test_committed_generated_scripts_are_up_to_date(tmp_path):
    for fresh in export_sql(tmp_path):
        committed = db.SQL_DIR / "generated" / fresh.parent.name / fresh.name
        assert committed.read_text(encoding="utf-8") == fresh.read_text(encoding="utf-8"), \
            f"{committed} is stale: run python -m sqldash export-sql"
