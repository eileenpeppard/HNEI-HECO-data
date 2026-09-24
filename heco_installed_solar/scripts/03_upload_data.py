#!/usr/bin/env python3
"""
03_upload_data.py

Uploads output\\heco_installed_pv.csv (built by 02_extract_pv_data.py) into
Postgres (hnei_heco database, statewide.installed_pv) via a single
`psql \\copy` transaction.

Connection info (host/user/password) is taken from the standard PG*
environment variables or ~/.pgpass -- nothing is hardcoded here.

On a successful upload, each PDF in input\\ whose quarter is in the CSV is
moved to archive\\. PDFs that 02_extract_pv_data.py could not read (and so
left out of the CSV) stay in input\\. If the upload fails -- including when a
quarter is already in the table, which the primary key rejects -- the whole
transaction is rolled back and nothing is archived.

Usage:
    python 03_upload_data.py
"""

import csv
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_DIR = BASE_DIR / "input"
ARCHIVE_DIR = BASE_DIR / "archive"
CSV_PATH = BASE_DIR / "output" / "heco_installed_pv.csv"

DATABASE = "hnei_heco"
TABLE = "statewide.installed_pv"
COLUMNS = (
    '"date", utility, num_systems, pct_systems_residential, pct_systems_commercial, '
    "capacity_mw, pct_capacity_residential, pct_capacity_commercial"
)


def build_transaction_sql() -> str:
    # psql wants forward slashes in the \copy path, even on Windows.
    csv_path = CSV_PATH.resolve().as_posix()
    return (
        "BEGIN;\n"
        f"\\copy {TABLE}({COLUMNS}) from '{csv_path}' CSV HEADER;\n"
        "COMMIT;\n"
    )


def pdf_name_for(as_of: str) -> str:
    """'2026-06-30' -> '2026_2Q_pv_summary.pdf'"""
    d = date.fromisoformat(as_of)
    return f"{d.year}_{(d.month - 1) // 3 + 1}Q_pv_summary.pdf"


def uploaded_pdf_names() -> list[str]:
    """Names of the input PDFs whose quarters are in the CSV."""
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        dates = sorted({row["date"] for row in csv.DictReader(f)})
    return [pdf_name_for(d) for d in dates]


def main():
    if not CSV_PATH.exists():
        sys.exit(f"CSV not found: {CSV_PATH}\nRun 02_extract_pv_data.py first.")

    pdf_names = uploaded_pdf_names()
    if not pdf_names:
        sys.exit(f"{CSV_PATH.name} has no data rows; nothing to upload.")

    print(f"Uploading {CSV_PATH.name} ({len(pdf_names)} quarter(s)) -> {TABLE}")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sql", delete=False, encoding="utf-8"
    ) as f:
        f.write(build_transaction_sql())
        script_path = Path(f.name)

    try:
        result = subprocess.run(
            ["psql", DATABASE, "-v", "ON_ERROR_STOP=1", "-f", str(script_path)]
        )
    finally:
        script_path.unlink(missing_ok=True)

    if result.returncode != 0:
        sys.exit(
            f"psql exited with status {result.returncode}; "
            "transaction rolled back, nothing archived."
        )
    print("Done.")

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archived = 0
    for name in pdf_names:
        pdf = INPUT_DIR / name
        if pdf.exists():
            shutil.move(str(pdf), str(ARCHIVE_DIR / name))
            archived += 1
        else:
            print(f"  (not in input\\, skipped: {name})")
    print(f"Archived {archived} PDF(s) to {ARCHIVE_DIR}")

    left = sorted(p.name for p in INPUT_DIR.glob("*.pdf"))
    if left:
        print(f"Left in input\\ (not in the CSV): {', '.join(left)}")


if __name__ == "__main__":
    main()
