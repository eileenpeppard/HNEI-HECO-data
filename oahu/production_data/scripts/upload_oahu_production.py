#!/usr/bin/env python3
"""
upload_oahu_production.py

Uploads the combined hourly generation CSV into oahu.production_mwh via
`psql \\copy`. Connection info (host/db/user/password) is taken from the
standard PG* environment variables or ~/.pgpass -- nothing is hardcoded here.

Once the upload succeeds, any raw Excel files still sitting in raw_data\\
(the ones reshape_hourly_generation_data.py folded into the combined CSV)
are moved to processed_data\\. They're archived here, after the DB write is
confirmed, rather than at reshape time, so a raw file is never archived
unless its data actually made it into the database.

Usage:
    python upload_oahu_production.py
"""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "raw_data"
PROCESSED_DIR = BASE_DIR / "processed_data"
CSV_PATH = BASE_DIR / "csv_output" / "combined_oahu_production_data.csv"

COPY_SQL = (
    '\\copy oahu.production_mwh(datetime,plant_name,mwh) '
    f"from '{CSV_PATH}' CSV HEADER;"
)


def archive_raw_files():
    raw_files = sorted(RAW_DIR.glob("*.xlsx")) + sorted(RAW_DIR.glob("*.xls"))
    if not raw_files:
        return

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for path in raw_files:
        dest = PROCESSED_DIR / path.name
        path.rename(dest)
        print(f"  Archived: {path.name} -> processed_data\\")


def main():
    if not CSV_PATH.exists():
        sys.exit(f"CSV not found: {CSV_PATH}")

    print(f"Uploading {CSV_PATH}\n  -> oahu.production_mwh")
    result = subprocess.run(["psql", "hnei_heco", "-v", "ON_ERROR_STOP=1", "-c", COPY_SQL])
    if result.returncode != 0:
        sys.exit(f"psql exited with status {result.returncode}")
    print("Done.")

    archive_raw_files()


if __name__ == "__main__":
    main()
