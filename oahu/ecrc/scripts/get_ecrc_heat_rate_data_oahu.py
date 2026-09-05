"""
extract_heat_rate.py

Extracts monthly recorded heat rate data from Hawaiian Electric ECRC heat rate PDFs.
Each filing's page reprints the full recorded-data history, so only the latest
(newest) month is taken from each PDF; that row is merged into the existing
output CSV so prior history is preserved across runs.

Usage:
    python extract_heat_rate.py                          # processes all PDFs in INPUT_DIR
    python extract_heat_rate.py path/to/file.pdf         # single file
    python extract_heat_rate.py --output results.csv     # custom output path
"""

import re
import sys
import csv
import argparse
from pathlib import Path
from calendar import monthrange
from datetime import date

# ── Dependencies ──────────────────────────────────────────────────────────────
try:
    import pdfplumber
except ImportError:
    sys.exit("Missing dependency: pip install pdfplumber")

# ── Config ────────────────────────────────────────────────────────────────────
INPUT_DIR = Path(__file__).resolve().parent.parent / "heat_rate"
OUTPUT_CSV = INPUT_DIR / "csv_output" / "heat_rate_extracted.csv"

# Matches lines like "Jan-25  11,055  11,055" or "Dec-24  11,608  11,340"
ROW_PATTERN = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(\d{2})"  # Mon-YY
    r"\s+([\d,]+)"           # monthly heat rate (col 1)
    r"(?:\s+([\d,]+))?",     # YTD heat rate (col 2, optional)
    re.IGNORECASE
)

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def last_day_of_month(year: int, month: int) -> date:
    """Return the last calendar day of the given year/month."""
    return date(year, month, monthrange(year, month)[1])


def parse_heat_rate_value(raw: str) -> int | None:
    """Strip commas and convert to int; return None on failure."""
    try:
        return int(raw.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def extract_from_text(text: str) -> list[tuple[date, int]]:
    """Parse all matching data rows from extracted PDF text."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        m = ROW_PATTERN.match(line)
        if not m:
            continue
        mon_str, yr_str, monthly_raw, _ = m.groups()
        month = MONTH_MAP[mon_str.lower()]
        year = 2000 + int(yr_str)
        value = parse_heat_rate_value(monthly_raw)
        if value is not None:
            obs_date = last_day_of_month(year, month)
            rows.append((obs_date, value))
    return rows


def extract_from_pdf(pdf_path: Path) -> list[tuple[date, int]]:
    """Open a PDF and extract only the most recent heat rate row.

    Each filing's page reprints the full recorded-data history, so only the
    latest month (the new data this filing actually adds) is kept.
    """
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            rows.extend(extract_from_text(text))
    if not rows:
        return []
    return [max(rows, key=lambda row: row[0])]


def load_existing(output_path: Path) -> dict[date, int]:
    """Load previously extracted rows so new runs merge with prior history."""
    seen: dict[date, int] = {}
    if not output_path.exists():
        return seen
    with open(output_path, newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        for row in reader:
            if not row:
                continue
            obs_date = date.fromisoformat(row[0])
            seen[obs_date] = int(row[1])
    return seen


def process_files(pdf_paths: list[Path], output_path: Path) -> None:
    all_rows: list[tuple[date, int]] = []

    for pdf_path in pdf_paths:
        print(f"Processing: {pdf_path.name}")
        rows = extract_from_pdf(pdf_path)
        print(f"  → {len(rows)} rows found")
        all_rows.extend(rows)

    if not all_rows:
        print("No data extracted. Check that the PDFs match the expected format.")
        return

    # Merge with existing output (if any), then dedupe (keep last seen) and sort
    seen = load_existing(output_path)
    for obs_date, value in all_rows:
        seen[obs_date] = value
    sorted_rows = sorted(seen.items())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "monthly_recorded_heat_rate_btu_kwh_sales"])
        for obs_date, value in sorted_rows:
            writer.writerow([obs_date.strftime("%Y-%m-%d"), value])

    print(f"\nDone. {len(sorted_rows)} unique rows written to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Extract ECRC heat rate data from PDFs.")
    parser.add_argument("pdfs", nargs="*", help="PDF file(s) to process (default: all in INPUT_DIR)")
    parser.add_argument("--output", default=str(OUTPUT_CSV), help="Output CSV path")
    args = parser.parse_args()

    output_path = Path(args.output)

    if args.pdfs:
        pdf_paths = [Path(p) for p in args.pdfs]
        missing = [p for p in pdf_paths if not p.exists()]
        if missing:
            sys.exit(f"File(s) not found: {missing}")
    else:
        if not INPUT_DIR.exists():
            sys.exit(f"Input directory not found: {INPUT_DIR}")
        pdf_paths = sorted(INPUT_DIR.glob("*.pdf"))
        if not pdf_paths:
            sys.exit(f"No PDF files found in: {INPUT_DIR}")
        print(f"Found {len(pdf_paths)} PDF(s) in {INPUT_DIR}")

    process_files(pdf_paths, output_path)


if __name__ == "__main__":
    main()