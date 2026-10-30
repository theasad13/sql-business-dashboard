from pathlib import Path

import pytest

from sqldash import db

FIXTURES = Path(__file__).parent / "fixtures"


def make_tiny(extra_sql: str = ""):
    conn = db.connect()
    db.create_schema(conn)
    conn.executescript((FIXTURES / "tiny.sql").read_text(encoding="utf-8"))
    if extra_sql:
        conn.executescript(extra_sql)
    db.install_views(conn)
    return conn


@pytest.fixture
def tiny():
    conn = make_tiny()
    yield conn
    conn.close()
