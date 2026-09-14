#!/usr/bin/env python3
"""
4.4_upload_purchased_energy_oahu.py

Uploads purchased_energy.csv into Postgres (oahu.purchased_energy) via a
single `psql \\copy` transaction.

Connection info (host/db/user/password) is taken from the standard PG*
environment variables or ~/.pgpass -- nothing is hardcoded here.

On a successful upload, purchased_energy.csv is deleted and any source PDFs
still sitting in purchased_component\\ are archived to
purchased_component\\processed_page\\. Each of the three purchased_component
upload scripts (4.4/4.5/4.6) does this independently, so PDFs already moved
by one of the others are simply skipped. If the upload fails, nothing is
archived or deleted -- fix the problem and rerun.

Usage:
    python 4.4_upload_purchased_energy_oahu.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PDF_DIR = Path(__file__).resolve().parent.parent / "purchased_component"
PROCESSED_DIR = PDF_DIR / "processed_page"
CSV_DIR = PDF_DIR / "csv_output"

CSV_PATH = CSV_DIR / "purchased_energy.csv"
TABLE = "oahu.purchased_energy"
COLUMNS = 'erc_name, "date", price_cents_per_kwh, "%_of_purchased"'


def build_transaction_sql() -> str:
    csv_path = CSV_PATH.resolve()
    return (
        "BEGIN;\n"
        f"\\copy {TABLE}({COLUMNS}) from '{csv_path}' CSV HEADER;\n"
        "COMMIT;\n"
    )


def main():
    if not CSV_PATH.exists():
        sys.exit(f"CSV not found: {CSV_PATH}")

    print(f"Uploading {CSV_PATH.name} -> {TABLE}")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sql", delete=False, encoding="utf-8"
    ) as f:
        f.write(build_transaction_sql())
        script_path = Path(f.name)

    try:
        result = subprocess.run(
            ["psql", "hnei_heco", "-v", "ON_ERROR_STOP=1", "-f", str(script_path)]
        )
    finally:
        script_path.unlink(missing_ok=True)

    if result.returncode != 0:
        sys.exit(
            f"psql exited with status {result.returncode}; "
            "transaction rolled back, nothing archived or deleted."
        )
    print("Done.")

    CSV_PATH.unlink()
    print(f"Removed {CSV_PATH}")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    for pdf in pdfs:
        shutil.move(str(pdf), str(PROCESSED_DIR / pdf.name))
    print(f"Archived {len(pdfs)} PDF(s) to {PROCESSED_DIR}")


if __name__ == "__main__":
    main()
