#!/usr/bin/env python3
"""
upload_ecrc_purchased_oahu.py

Uploads the processed purchased energy CSV into oahu.purchased_energy via
`psql \\copy`. Connection info (host/db/user/password) is taken from the
standard PG* environment variables or ~/.pgpass -- nothing is hardcoded here.

On a successful upload, the source PDFs sitting in purchased_component\\ are
archived to purchased_component\\processed_page\\ and the final CSV is
deleted, so the next run's get_ecrc_purchased_data_oahu.py only picks up new
filings. Per-stage debug CSVs under csv_output\\_intermediate\\ are left
alone.

Usage:
    python upload_ecrc_purchased_oahu.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

PDF_DIR = Path(__file__).resolve().parent.parent / "purchased_component"
PROCESSED_DIR = PDF_DIR / "processed_page"
CSV_PATH = PDF_DIR / "csv_output" / "purchased_energy.csv"

COPY_SQL = (
    '\\copy oahu.purchased_energy(erc_name, "date", price_cents_per_kwh, "%_of_purchased") '
    f"from '{CSV_PATH}' CSV HEADER;"
)


def main():
    if not CSV_PATH.exists():
        sys.exit(f"CSV not found: {CSV_PATH}")

    print(f"Uploading {CSV_PATH}\n  -> oahu.purchased_energy")
    result = subprocess.run(["psql", "hnei_heco", "-v", "ON_ERROR_STOP=1", "-c", COPY_SQL])
    if result.returncode != 0:
        sys.exit(f"psql exited with status {result.returncode}")
    print("Done.")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    for pdf in pdfs:
        shutil.move(str(pdf), str(PROCESSED_DIR / pdf.name))
    print(f"Archived {len(pdfs)} PDF(s) to {PROCESSED_DIR}")

    CSV_PATH.unlink()
    print(f"Removed {CSV_PATH}")


if __name__ == "__main__":
    main()
