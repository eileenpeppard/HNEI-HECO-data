#!/usr/bin/env python3
"""
upload_ecrc_purchased_oahu.py

Uploads the three processed purchased_component CSVs into Postgres via a
single `psql \\copy` transaction:

    purchased_energy.csv           -> oahu.purchased_energy
    purchased_cost_components.csv  -> oahu.purchased_cost_components
    purchased_composite.csv        -> oahu.purchased_composite

All three \\copy commands run inside one BEGIN/COMMIT block so they succeed
or fail together. The three CSVs are derived from the same batch of PDFs,
so a partial upload would be worse than no upload: if CSV #2 failed after
CSV #1 already committed, a retry after fixing the problem would re-insert
CSV #1's rows as duplicates, since its source PDFs are archived away as
soon as any upload succeeds. Wrapping all three in one transaction means a
failure partway through leaves the database completely untouched.

Connection info (host/db/user/password) is taken from the standard PG*
environment variables or ~/.pgpass -- nothing is hardcoded here.

On a successful upload, the source PDFs sitting in purchased_component\\ are
archived to purchased_component\\processed_page\\ and all three CSVs are
deleted, so the next run of 4.1/4.2/4.3 only picks up new filings. Per-stage
debug CSVs under csv_output\\_intermediate\\ are left alone. If the upload
fails, nothing is archived or deleted -- fix the problem and rerun.

Usage:
    python 4.4_upload_ecrc_purchased_oahu.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PDF_DIR = Path(__file__).resolve().parent.parent / "purchased_component"
PROCESSED_DIR = PDF_DIR / "processed_page"
CSV_DIR = PDF_DIR / "csv_output"

# Table and column names mirror the CSV filenames/headers exactly.
UPLOADS = [
    {
        "csv": CSV_DIR / "purchased_energy.csv",
        "table": "oahu.purchased_energy",
        "columns": 'erc_name, "date", price_cents_per_kwh, "%_of_purchased"',
    },
    {
        "csv": CSV_DIR / "purchased_cost_components.csv",
        "table": "oahu.purchased_cost_components",
        "columns": '"date", component, value',
    },
    {
        "csv": CSV_DIR / "purchased_composite.csv",
        "table": "oahu.purchased_composite",
        "columns": (
            'month, purchased_price_cents_per_kwh_fossil, '
            'purchased_price_cents_per_kwh_renewable, '
            'purchased_price_cents_per_kwh_composite, "date", '
            '"purchased_input_into_system_mix_%", "renewable/fossil_price"'
        ),
    },
]


def build_transaction_sql() -> str:
    lines = ["BEGIN;"]
    for upload in UPLOADS:
        csv_path = upload["csv"].resolve()
        lines.append(
            f"\\copy {upload['table']}({upload['columns']}) "
            f"from '{csv_path}' CSV HEADER;"
        )
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


def main():
    missing = [str(u["csv"]) for u in UPLOADS if not u["csv"].exists()]
    if missing:
        sys.exit("CSV(s) not found:\n  " + "\n  ".join(missing))

    print("Uploading (single transaction):")
    for upload in UPLOADS:
        print(f"  {upload['csv'].name} -> {upload['table']}")

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

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    for pdf in pdfs:
        shutil.move(str(pdf), str(PROCESSED_DIR / pdf.name))
    print(f"Archived {len(pdfs)} PDF(s) to {PROCESSED_DIR}")

    for upload in UPLOADS:
        upload["csv"].unlink()
        print(f"Removed {upload['csv']}")


if __name__ == "__main__":
    main()
