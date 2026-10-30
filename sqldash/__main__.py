"""Command line: python -m sqldash <command>.

  demo         build the sample DB, print KPIs, write dashboard + Power BI CSVs (+ open the dashboard)
  build        build the sample DB only (or --from-csv DIR to load your own data)
  report       print the KPIs and data-quality checks for an existing DB
  dashboard    write the HTML dashboard for an existing DB
  powerbi      write star-schema CSVs for an existing DB
  export-sql   write SQL Server / PostgreSQL versions of the SQL scripts
  screenshot   save PNG screenshots of the dashboard with a local Edge/Chrome (headless)
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from . import dashboard, db, generate, kpis, powerbi
from .dialects import render

ROOT = db.ROOT
DEFAULT_DB = ROOT / "build" / "business.db"
DEFAULT_HTML = ROOT / "examples" / "dashboard.html"
DEFAULT_PBI = ROOT / "examples" / "powerbi"


def _money(v) -> str:
    return "-" if v is None else f"${v:,.2f}"


def _pct(v) -> str:
    return "-" if v is None else f"{v:.1f}%"


def print_report(conn) -> None:
    h = kpis.headline(conn)
    print(f"\nKPIs (receivables as of {kpis.report_date(conn)})")
    print(f"  Revenue           {_money(h['revenue'])}")
    print(f"  Gross margin      {_money(h['gross_margin'])} ({_pct(h['gross_margin_pct'])})")
    print(f"  Orders            {h['orders']:,}   Active customers {h['active_customers']:,}")
    print(f"  Avg order value   {_money(h['avg_order_value'])}")
    print(f"  Receivables       {_money(h['ar_outstanding'])}  overdue {_money(h['ar_overdue'])} ({_pct(h['ar_overdue_pct'])})")
    print("\nReceivables aging")
    for a in kpis.aging(conn):
        print(f"  {a['aging_bucket']:<12} {a['open_invoices']:>5} invoices  {_money(a['outstanding']):>14}  {_pct(a['pct_of_total']):>6}")
    print("\nRevenue by region")
    for r in kpis.regions(conn):
        print(f"  {r['region_name']:<10} {_money(r['revenue']):>15}  {_pct(r['revenue_share_pct']):>6}")
    print("\nTop 5 products")
    for p in kpis.products(conn, 5):
        print(f"  {p['revenue_rank']}. {p['product_name']:<28} {_money(p['revenue']):>14}")
    print("\nData-quality checks")
    for d in kpis.dq_summary(conn):
        mark = "OK  " if d["failing_rows"] == 0 else ("FAIL" if d["severity"] == "error" else "WARN")
        print(f"  [{mark}] {d['check_name']:<28} {d['failing_rows']:>3} rows  {d['description']}")


def export_sql(out_dir: Path) -> list[Path]:
    written = []
    for dialect in ("sqlserver", "postgres"):
        target = out_dir / dialect
        target.mkdir(parents=True, exist_ok=True)
        for name in db.SQL_FILES:
            path = target / name
            path.write_text(f"-- GENERATED from sql/{name} by `python -m sqldash export-sql`. Do not edit by hand.\n"
                            + db.read_sql(name, dialect), encoding="utf-8")
            written.append(path)
    return written


def find_browser() -> str | None:
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    for name in ("msedge", "google-chrome", "chromium", "chromium-browser", "chrome"):
        if found := shutil.which(name):
            return found
    return None


def screenshot(html: Path, out_dir: Path) -> list[Path]:
    browser = find_browser()
    if not browser:
        raise SystemExit("No Edge/Chrome found for screenshots; open examples/dashboard.html and capture by hand.")
    out_dir.mkdir(parents=True, exist_ok=True)
    shots = []
    for name, size in (("dashboard-desktop.png", "1400,2650"), ("dashboard-mobile.png", "390,5200")):
        out = out_dir / name
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-color-profile=srgb",
                        f"--window-size={size}", f"--screenshot={out}", html.resolve().as_uri()],
                       check=True, capture_output=True, timeout=120)
        shots.append(out)
    return shots


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m sqldash", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["demo", "build", "report", "dashboard", "powerbi", "export-sql", "screenshot"])
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite file (default build/business.db)")
    ap.add_argument("--seed", type=int, default=42, help="random seed for the sample data")
    ap.add_argument("--from-csv", type=Path, help="build: load your own CSVs (one per table) instead of sample data")
    ap.add_argument("--report-date", help="build --from-csv: the 'as of' date, YYYY-MM-DD")
    ap.add_argument("--out", type=Path, help="output file/folder for dashboard, powerbi, export-sql, screenshot")
    ap.add_argument("--no-open", action="store_true", help="demo: don't open the dashboard in a browser")
    args = ap.parse_args(argv)

    if args.command in ("demo", "build"):
        if args.from_csv:
            if not args.report_date:
                ap.error("--from-csv needs --report-date YYYY-MM-DD")
            conn = db.build_from_csv(args.db, args.from_csv, args.report_date)
        else:
            conn = db.build(args.db, generate.generate(seed=args.seed))
        print(f"Database: {args.db}")
    elif args.command in ("report", "dashboard", "powerbi"):
        if not args.db.exists():
            ap.error(f"{args.db} not found; run `python -m sqldash build` first")
        conn = db.connect(args.db)

    if args.command in ("demo", "report"):
        print_report(conn)
    if args.command in ("demo", "dashboard"):
        out = dashboard.write(conn, args.out or DEFAULT_HTML)
        print(f"\nDashboard: {out}")
    if args.command in ("demo", "powerbi"):
        target = args.out if args.command == "powerbi" and args.out else DEFAULT_PBI
        counts = powerbi.export(conn, target)
        print(f"Power BI CSVs: {target}  ({', '.join(f'{k} {v:,}' for k, v in counts.items())})")
    if args.command == "export-sql":
        for p in export_sql(args.out or ROOT / "sql" / "generated"):
            print(p)
    if args.command == "screenshot":
        for p in screenshot(DEFAULT_HTML, args.out or ROOT / "examples"):
            print(p)
    if args.command == "demo" and not args.no_open:
        webbrowser.open((args.out or DEFAULT_HTML).resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
