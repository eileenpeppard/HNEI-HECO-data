#!/usr/bin/env python3
"""
upload_ecrc_foac_oahu.py

Uploads the extracted FOAC fuel data CSV into oahu.fuel_oil via `psql \\copy`.
Connection info (host/db/user/password) is taken from the standard PG*
environment variables or ~/.pgpass -- nothing is hardcoded here, so this
runs the same way on the server as it does anywhere else psql is configured.

On a successful upload, the source PDFs sitting in foac_biodiesel\\ are
archived to foac_biodiesel\\processed_page\\ and the CSV is deleted, so the
next run's get_ecrc_foac_data_oahu.py only picks up new filings.

Usage:
    python upload_ecrc_foac_oahu.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

PDF_DIR = Path(__file__).resolve().parent.parent / "foac_biodiesel"
PROCESSED_DIR = PDF_DIR / "processed_page"
CSV_PATH = PDF_DIR / "csv_output" / "foac_fuel_data.csv"

COPY_SQL = (
    '\\copy oahu.fuel_oil ("date",fuel,barrels,mbtus,amount_$,"avg_$/mbtu","avg_$/bbl") '
    f"from '{CSV_PATH}' CSV HEADER;"
)


def main():
    if not CSV_PATH.exists():
        sys.exit(f"CSV not found: {CSV_PATH}")

    print(f"Uploading {CSV_PATH}\n  -> oahu.fuel_oil")
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
