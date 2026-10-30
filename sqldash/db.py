"""Create the SQLite database, load data, install views; read query results as dicts."""
from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path

from .dialects import render
from .generate import Dataset

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"
SQL_FILES = ("schema.sql", "views.sql", "dq_checks.sql")
TABLES = ("regions", "customers", "products", "orders", "order_items", "payments", "report_params")


def read_sql(name: str, dialect: str = "sqlite") -> str:
    return render((SQL_DIR / name).read_text(encoding="utf-8"), dialect)


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(read_sql("schema.sql"))


def install_views(conn: sqlite3.Connection) -> None:
    conn.executescript(read_sql("views.sql"))
    conn.executescript(read_sql("dq_checks.sql"))


def load_dataset(conn: sqlite3.Connection, ds: Dataset) -> None:
    for table, rows in ds.tables().items():
        if rows:
            marks = ",".join("?" * len(rows[0]))
            conn.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
    conn.commit()


def build(path: str | Path, ds: Dataset) -> sqlite3.Connection:
    """Fresh database file at `path` with schema, data and views."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = connect(path)
    create_schema(conn)
    load_dataset(conn, ds)
    install_views(conn)
    return conn


def build_from_csv(path: str | Path, csv_dir: str | Path, report_date: str) -> sqlite3.Connection:
    """Fresh database from one CSV per source table (header row = column names)."""
    path, csv_dir = Path(path), Path(csv_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = connect(path)
    create_schema(conn)
    for table in TABLES[:-1]:
        file = csv_dir / f"{table}.csv"
        if not file.exists():
            raise FileNotFoundError(f"missing {file} (need one CSV per table: {', '.join(TABLES[:-1])})")
        with file.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            cols = reader.fieldnames or []
            rows = [[(row[c] if row[c] != "" else None) for c in cols] for row in reader]
        if rows:
            conn.executemany(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", rows)
    conn.execute("INSERT INTO report_params VALUES (?)", (report_date,))
    conn.commit()
    install_views(conn)
    return conn


def rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def view_sql(name: str) -> str:
    """The CREATE VIEW text for one view (SQLite flavour), for showing in the dashboard/README."""
    for file in ("views.sql", "dq_checks.sql"):
        text = read_sql(file)
        m = re.search(rf"-- view: {name}\n(.*?;)\n", text, flags=re.S)
        if m:
            return m.group(1).strip()
    raise KeyError(name)
