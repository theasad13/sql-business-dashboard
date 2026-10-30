"""Expand the three SQL macros (@MONTH, @MONTH_INDEX, @DAYS_BETWEEN) per database.

The SQL files are written once; this module turns them into SQLite, SQL Server
or PostgreSQL scripts. Kept tiny on purpose so a reviewer can check it by eye.
"""
from __future__ import annotations

import re

DIALECTS = ("sqlite", "sqlserver", "postgres")

_MACROS = {
    "sqlite": {
        "MONTH": lambda d: f"strftime('%Y-%m', {d})",
        "MONTH_INDEX": lambda d: f"(CAST(strftime('%Y', {d}) AS INTEGER) * 12 + CAST(strftime('%m', {d}) AS INTEGER))",
        "DAYS_BETWEEN": lambda a, b: f"CAST(julianday({b}) - julianday({a}) AS INTEGER)",
    },
    "sqlserver": {
        "MONTH": lambda d: f"CONVERT(CHAR(7), {d}, 126)",
        "MONTH_INDEX": lambda d: f"(YEAR({d}) * 12 + MONTH({d}))",
        "DAYS_BETWEEN": lambda a, b: f"DATEDIFF(day, {a}, {b})",
    },
    "postgres": {
        "MONTH": lambda d: f"to_char({d}, 'YYYY-MM')",
        "MONTH_INDEX": lambda d: f"(CAST(EXTRACT(YEAR FROM {d}) AS INTEGER) * 12 + CAST(EXTRACT(MONTH FROM {d}) AS INTEGER))",
        "DAYS_BETWEEN": lambda a, b: f"(CAST({b} AS DATE) - CAST({a} AS DATE))",
    },
}

_MACRO_START = re.compile(r"@([A-Z_]+)\(")


def _split_args(text: str) -> list[str]:
    """Split 'a, f(b, c)' on top-level commas only."""
    args, depth, current = [], 0, ""
    for ch in text:
        if ch == "," and depth == 0:
            args.append(current.strip())
            current = ""
            continue
        depth += ch == "("
        depth -= ch == ")"
        current += ch
    args.append(current.strip())
    return args


def render(sql: str, dialect: str) -> str:
    """Return `sql` with every macro expanded for `dialect`."""
    if dialect not in DIALECTS:
        raise ValueError(f"unknown dialect {dialect!r}; use one of {DIALECTS}")
    sql = _expand(sql, _MACROS[dialect])
    return _sqlserver_batches(sql) if dialect == "sqlserver" else sql


def _expand(sql: str, macros: dict) -> str:
    pos = 0
    while (m := _MACRO_START.search(sql, pos)) is not None:
        line_start = sql.rfind("\n", 0, m.start()) + 1
        if "--" in sql[line_start:m.start()]:  # leave macros in comments alone
            pos = m.end()
            continue
        name = m.group(1)
        if name not in macros:
            raise ValueError(f"unknown macro @{name}")
        depth, i = 1, m.end()
        while depth:
            if i >= len(sql):
                raise ValueError(f"unclosed @{name}(")
            depth += sql[i] == "("
            depth -= sql[i] == ")"
            i += 1
        args = [_expand(a, macros) for a in _split_args(sql[m.end():i - 1])]
        sql = sql[:m.start()] + macros[name](*args) + sql[i:]
        pos = m.start()
    return sql


def _sqlserver_batches(sql: str) -> str:
    """SQL Server wants each CREATE VIEW in its own batch: add GO after every statement."""
    return re.sub(r";[ \t]*\n", ";\nGO\n", sql if sql.endswith("\n") else sql + "\n")


def split_statements(sql: str) -> list[str]:
    """Split a rendered script into statements (semicolon at end of line)."""
    parts = re.split(r";[ \t]*(?:\n|$)", sql)
    return [p.strip() for p in parts if p.strip() and not _only_comments(p)]


def _only_comments(chunk: str) -> bool:
    return all(not line.strip() or line.strip().startswith("--") for line in chunk.splitlines())
