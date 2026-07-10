"""
extract_foac_data.py

Reads every single-page PDF in the FOAC folder, extracts fuel data,
and writes all rows to a CSV file.

Columns: date, fuel, barrels, mbtus, amount, avg_$/mbtu, avg_$/bbl

avg_$/mbtu  = amount / mbtus    (blank when barrels=mbtus=amount=0)
avg_$/bbl   = amount / barrels  (blank when barrels=mbtus=amount=0)

Handles:
  - PDFs where digits are split by invisible spaces (e.g. '8 10,484' → '810,484')
    by reconstructing text from raw character positions, ignoring space glyphs
  - Negative amounts expressed as ( 9,251,089) or -9,251,089
  - Older filings with PAGE 2 OF 4 (not just PAGE 2 OF 3)
  - Older filings missing some fuel labels (rows simply omitted)
  - Dates with no day: "FOAC February 2015" → 2/1/15
  - Fuel label words merged in extracted text: "WAIAUDIESEL" still matched

Requirements (conda):
    pdfplumber
"""

import csv
import re
from collections import defaultdict
from pathlib import Path

import pdfplumber

# ── Paths ──────────────────────────────────────────────────────────────────────
PDF_DIR    = Path(__file__).resolve().parent.parent / "foac_biodiesel"
OUTPUT_CSV = PDF_DIR / "csv_output" / "foac_fuel_data.csv"

# ── Fuel labels to extract ─────────────────────────────────────────────────────
# Rows for labels absent from a given filing are simply skipped (not an error).
FUEL_LABELS = [
    "LSFO",
    "WAIAU DIESEL",
    "CIP BIODIESEL",
    "CIP DIESEL",
    "SGS ULSD",
    "SGS BIODIESEL",
]

CSV_HEADER = ["date", "fuel", "barrels", "mbtus", "amount", "avg_$/mbtu", "avg_$/bbl"]

MONTH_MAP = {
    "january": 1,  "february": 2,  "march":     3, "april":    4,
    "may":     5,  "june":     6,  "july":      7, "august":   8,
    "september":9, "october": 10,  "november": 11, "december": 12,
}

# Matches parenthesised negatives (with optional internal space), minus-negatives,
# plain numbers (with commas/decimals), and bare dash (= zero)
_NUM_RE = re.compile(r'\(\s*[\d,]+(?:\.\d+)?\)|-[\d,]+(?:\.\d+)?|[\d,]+(?:\.\d+)?|-')


# ── Text extraction ────────────────────────────────────────────────────────────

def extract_text_clean(pdf_path: Path) -> str:
    """
    Reconstruct page text from raw character positions, completely ignoring
    space glyphs. This fixes PDFs where numbers are split by invisible spaces
    (e.g. '8 10,484' should be '810,484').

    Characters within 8 pts of each other horizontally are merged into one token.
    Tokens on the same line are joined with a single space.
    Lines are ordered top-to-bottom.
    """
    with pdfplumber.open(pdf_path) as pdf:
        chars = [c for c in pdf.pages[0].chars if c['text'] != ' ']

    # Group characters by rounded y position (= same line)
    lines: dict = defaultdict(list)
    for ch in chars:
        lines[round(ch['y0'])].append(ch)

    result_lines = []
    for y_key in sorted(lines.keys(), reverse=True):   # reverse = top-to-bottom
        line_chars = sorted(lines[y_key], key=lambda c: c['x0'])
        tokens  = []
        current = line_chars[0]['text']
        for prev, curr in zip(line_chars, line_chars[1:]):
            gap = curr['x0'] - prev['x1']
            if gap <= 8:          # close enough → same token
                current += curr['text']
            else:
                tokens.append(current)
                current = curr['text']
        tokens.append(current)
        result_lines.append(' '.join(tokens))

    return '\n'.join(result_lines)


# ── Date parsing ───────────────────────────────────────────────────────────────

def parse_date(text: str) -> str | None:
    """
    Handles:
      "FOAC March 1, 2026"  → "3/1/26"
      "FOACApril2018"       → "4/1/18"   (words merged, no day)
      "FOAC February 2015"  → "2/1/15"   (no day)
    Uses \s* so it works whether or not words were merged during extraction.
    """
    # With day
    m = re.search(
        r"FOAC\s*(January|February|March|April|May|June|July|"
        r"August|September|October|November|December)\s*(\d{1,2}),?\s*(\d{4})",
        text, re.IGNORECASE,
    )
    if m:
        month = MONTH_MAP[m.group(1).lower()]
        day   = int(m.group(2))
        year  = m.group(3)[-2:]
        return f"{month}/{day}/{year}"

    # Without day
    m = re.search(
        r"FOAC\s*(January|February|March|April|May|June|July|"
        r"August|September|October|November|December)\s*(\d{4})",
        text, re.IGNORECASE,
    )
    if m:
        month = MONTH_MAP[m.group(1).lower()]
        year  = m.group(2)[-2:]
        return f"{month}/1/{year}"

    return None


# ── Number parsing ─────────────────────────────────────────────────────────────

def parse_number(token: str) -> float:
    """
    Convert a matched number token to float.
      "1,234"        →  1234.0
      "( 9,251,089)" → -9251089.0
      "(9,251,089)"  → -9251089.0
      "-9,251,089"   → -9251089.0
      "-"            →  0.0
    """
    token = token.strip()
    if token == "-":
        return 0.0
    negative = token.startswith("(") and token.endswith(")")
    clean = token.replace(" ", "").replace("(", "").replace(")", "").replace(",", "")
    return (-1 if negative else 1) * float(clean)


# ── Fuel block extraction ──────────────────────────────────────────────────────

def label_pattern(label: str) -> re.Pattern:
    """
    Build a regex that matches the label whether or not its words are merged.
    E.g. "WAIAU DIESEL" matches "WAIAU DIESEL" or "WAIAUDIESEL".
    """
    return re.compile(r'\s*'.join(re.escape(w) for w in label.split()), re.IGNORECASE)


def extract_fuel_block(text: str, fuel_label: str) -> tuple[float, float, float] | None:
    """
    Find the fuel label line and return (barrels, mbtus, amount).
    Returns None if the label is not present in this filing.
    """
    lm = label_pattern(fuel_label).search(text)
    if not lm:
        return None

    after  = text[lm.end(): lm.end() + 200]
    tokens = _NUM_RE.findall(after)
    if len(tokens) < 3:
        tokens += ["-"] * (3 - len(tokens))

    return parse_number(tokens[0]), parse_number(tokens[1]), parse_number(tokens[2])


# ── Row builder ────────────────────────────────────────────────────────────────

def build_row(date: str, fuel: str, barrels: float, mbtus: float, amount: float) -> dict:
    all_zero = (barrels == 0 and mbtus == 0 and amount == 0)
    avg_mbtu = "" if (all_zero or mbtus   == 0) else amount / mbtus
    avg_bbl  = "" if (all_zero or barrels == 0) else amount / barrels

    def fmt_rate(v) -> str:
        return f"{v:.6f}" if v != "" else ""

    return {
        "date":       date,
        "fuel":       fuel,
        "barrels":    f"{int(barrels)}" if barrels != 0 else "0",
        "mbtus":      f"{mbtus:.2f}"    if mbtus   != 0 else "0",
        "amount":     f"{amount:.2f}"   if amount  != 0 else "0",
        "avg_$/mbtu": fmt_rate(avg_mbtu),
        "avg_$/bbl":  fmt_rate(avg_bbl),
    }


# ── Per-PDF processor ──────────────────────────────────────────────────────────

def process_pdf(pdf_path: Path) -> list[dict]:
    rows = []
    try:
        text = extract_text_clean(pdf_path)
    except Exception as exc:
        print(f"  [ERROR reading {pdf_path.name}] {exc}")
        return rows

    # Accept PAGE 2 OF 3, PAGE 2 OF 4, etc.
    t_upper = text.upper().replace(" ", "")
    if "ATTACHMENT3" not in t_upper or not re.search(r"PAGE2OF\d+", t_upper):
        print(f"  [WARN] {pdf_path.name} does not look like a FOAC page — skipping")
        return rows

    date = parse_date(text)
    if not date:
        print(f"  [WARN] Could not parse date from {pdf_path.name} — using filename")
        date = pdf_path.stem

    for fuel in FUEL_LABELS:
        result = extract_fuel_block(text, fuel)
        if result is None:
            continue    # fuel absent in this filing — not an error
        barrels, mbtus, amount = result
        rows.append(build_row(date, fuel, barrels, mbtus, amount))

    return rows


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in:\n  {PDF_DIR}")
        return

    print(f"Found {len(pdf_files)} PDF(s).\n")

    all_rows = []
    for pdf_path in pdf_files:
        print(f"[PROC]  {pdf_path.name}")
        rows = process_pdf(pdf_path)
        print(f"        {len(rows)} fuel row(s) extracted")
        all_rows.extend(rows)

    if not all_rows:
        print("\nNo data extracted.")
        return

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nWrote {len(all_rows)} rows to:\n  {OUTPUT_CSV}")


if __name__ == "__main__":
    main()