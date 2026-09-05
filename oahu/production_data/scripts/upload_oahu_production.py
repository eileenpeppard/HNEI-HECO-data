#!/usr/bin/env python3
"""
upload_oahu_production.py

Uploads the combined hourly generation CSV into oahu.production_mwh via
`psql \\copy`. Connection info (host/db/user/password) is taken from the
standard PG* environment variables or ~/.pgpass -- nothing is hardcoded here.

Usage:
    python upload_oahu_production.py
"""

import subprocess
import sys
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent.parent / "csv_output" / "combined_oahu_production_data.csv"

COPY_SQL = (
    '\\copy oahu.production_mwh(datetime,plant_name,mwh) '
    f"from '{CSV_PATH}' CSV HEADER;"
)


def main():
    if not CSV_PATH.exists():
        sys.exit(f"CSV not found: {CSV_PATH}")

    print(f"Uploading {CSV_PATH}\n  -> oahu.production_mwh")
    result = subprocess.run(["psql", "hnei_heco", "-v", "ON_ERROR_STOP=1", "-c", COPY_SQL])
    if result.returncode != 0:
        sys.exit(f"psql exited with status {result.returncode}")
    print("Done.")


if __name__ == "__main__":
    main()
