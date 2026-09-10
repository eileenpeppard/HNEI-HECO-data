"""
get_purchased_cost_components_oahu.py

Extracts the "cost component" summary values from HECO ECRC
purchased_component filings: the composite-cost calc block (lines 87c, 87d,
88-100, left column) and the "SYSTEM COMPOSITE" block (lines 124-138, right
column). These are the lines get_ecrc_purchased_data_oahu.py (4.1)
intentionally leaves out of its price/percentage reshape.

Output is long format: one row per (date, component) pair.

Usage:
    python 4.2_get_purchased_cost_components_oahu.py
"""

import re
import statistics
from datetime import datetime
from pathlib import Path

import pdfplumber
import pandas as pd

# -------------------------------------------------
# PATHS
# -------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent / "purchased_component"
OUTPUT_DIR = BASE_DIR / "csv_output"
FINAL_CSV = OUTPUT_DIR / "purchased_cost_components.csv"

# -------------------------------------------------
# LINE ID -> CANONICAL COMPONENT NAME
# -------------------------------------------------
# Left column: spatial extraction (same table as lines 48-100 in 4.1)
LEFT_SIDE_COMPONENTS = {
    "87c": "Composite Cost of Purchased Energy, Fossil",
    "87d": "Composite Cost of Purchased Energy, Renewable",
    "88": "Composite Cost of Purchased Energy",
    "89": "% Input to System kWh Mix",
    "90": "WTD CMP Purch Energy Cost (Gross)",
    "91": "2017 TY Loss Factor",
    "92": "WTD CMP Purch Energy Cost (Net)",
    "98": "Cost Less Base",
    "99": "Revenue Tax Adjustment (1 / (1-0.08885))",
    "100": "Purchased Energy Factor",
}

# Right column: text-scanning extraction ("SYSTEM COMPOSITE" box)
RIGHT_SIDE_COMPONENTS = {
    "124": "Gen and Purchased Energy Factor",
    "125": "Future Use Adjustment",
    "126": "ECR Reconciliation Adjustment",
    "127": "Non-Adjustable Component",
    "128": "Fossil Fuel Cost Risk Sharing Component",
    "129": "Monthly Energy Cost Recovery Factor",
    "130": "Baseline ECRC Component",
    "131": "Monthly Energy Cost Recovery Factor Less Baseline ECRC Component",
    "132": "Daytime System Load",
    "133": "Overnight System Load",
    "134": "Evening Peak System Load",
    "135": "Daytime Time-of-Use Monthly Energy Cost Recovery Factor",
    "136": "Overnight Time-of-Use Monthly Energy Cost Recovery Factor",
    "137": "Evening Peak Time-of-Use Monthly Energy Cost Recovery Factor",
    "138": "Composite",
}

# -------------------------------------------------
# REGEX HELPERS (mirrors 4.1_get_ecrc_purchased_data_oahu.py)
# -------------------------------------------------
float_pattern = re.compile(r'^[+-]?\d+\.\d+$')
five_decimal_pattern = re.compile(r'^\d+\.\d{5}$')   # Special for line 90
line_id_pattern = re.compile(r'^\d+(\.\d+)?[A-Za-z]?$')
decimal_pattern = re.compile(r'\(?\s*(-?\d+\.\d+)\s*\)?%?')


def mid_y(w):
    return (w["top"] + w["bottom"]) / 2.0


def normalize_decimal_spacing(line: str) -> str:
    """
    Some filings render an unparenthesized right-column value with a stray
    space around the decimal point (e.g. "6 .254" instead of "6.254"), which
    breaks decimal_pattern. Left unfixed, this doesn't just drop the value --
    the same-line match fails and the caller falls back to scanning nearby
    lines, silently picking up an unrelated number instead (e.g. line 131
    grabbing line 132's "Daytime System Load" figure). Collapse the spacing
    before any matching happens.
    """
    return re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', line)


def extract_effective_date(text: str) -> str | None:
    """Extracts 'Effective Date - September 1, 2025' -> '2025-09-01'."""
    pat = re.compile(
        r"Effective\s+Date\s*-\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        re.IGNORECASE,
    )
    m = pat.search(text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1).strip(), "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def system_composite_start(lines: list[str]) -> int:
    """
    Index of the first line at/after the 'SYSTEM COMPOSITE' header, i.e.
    where lines 124-138 actually live. Searching the right column for a bare
    line number (e.g. "135") without this bound can false-match a trailing
    fragment of an unrelated comma-formatted figure earlier on the page
    (e.g. "...budget 2,958,135" contains "135" as its own \\b-bounded word).
    """
    for i, ln in enumerate(lines):
        if "SYSTEM COMPOSITE" in ln.upper():
            return i
    return 0


def find_value_for_right_line(line_id: str, lines: list[str], start: int = 0) -> str | None:
    """
    Text-scan the right column for a line id and pull its decimal value.
    Handles negative values written as (1.2345) and the line-129 special
    case, where the value sits on the next physical line
    ("(lines 124 + 125 + 126 + 127 + 128) 18.775").
    """
    target = line_id.strip()

    for i, ln in enumerate(lines):
        if i < start:
            continue
        pattern = rf'\b{re.escape(target)}\b'
        if not re.search(pattern, ln):
            continue

        if target == "129":
            for j in range(i + 1, min(i + 4, len(lines))):
                if "lines 124" in lines[j] or "(lines 124" in lines[j]:
                    matches = list(decimal_pattern.finditer(lines[j]))
                    if matches:
                        full = matches[-1].group(0)
                        num = matches[-1].group(1)
                        if full.strip().startswith("(") and full.strip().endswith(")"):
                            if not num.startswith("-"):
                                num = "-" + num
                        return num

        matches = list(decimal_pattern.finditer(ln))
        if matches:
            full = matches[-1].group(0)
            num = matches[-1].group(1)
            if full.strip().startswith("(") and full.strip().endswith(")"):
                if not num.startswith("-"):
                    num = "-" + num
            return num

        for j in range(i + 1, min(i + 4, len(lines))):
            matches = list(decimal_pattern.finditer(lines[j]))
            if matches:
                full = matches[-1].group(0)
                num = matches[-1].group(1)
                if full.strip().startswith("(") and full.strip().endswith(")"):
                    if not num.startswith("-"):
                        num = "-" + num
                return num

    return None


def extract_left_side_values(words: list[dict]) -> dict[str, str]:
    """Spatially match decimal values to line-id labels in the left column."""
    values: dict[str, str] = {}

    decimal_words = [w for w in words if float_pattern.match(w["text"])]
    xs_values = [w["x0"] for w in decimal_words if w["x0"] > 100]
    left_xs = [x for x in xs_values if x < 400]
    if not left_xs:
        return values

    left_val_x = statistics.mean(left_xs)
    tolerance_x = 20

    id_words = [
        w for w in words
        if 60 <= w["x0"] <= 100 and line_id_pattern.match(w["text"])
    ]
    if not id_words:
        return values

    for vw in decimal_words:
        if abs(vw["x0"] - left_val_x) > tolerance_x:
            continue
        yv = mid_y(vw)
        closest_id_word = min(id_words, key=lambda iw: abs(mid_y(iw) - yv))
        line_id = closest_id_word["text"]

        # Line 90's value sits almost exactly between the 89 and 91 labels;
        # its 5-decimal precision is what distinguishes it from its neighbors.
        if five_decimal_pattern.match(vw["text"]) and line_id in ("89", "91"):
            line_id = "90"

        if line_id in LEFT_SIDE_COMPONENTS:
            values[line_id] = vw["text"]

    return values


def clean_value(raw: str) -> str:
    """Drop insignificant trailing zeros; render whole numbers without a decimal.

    Returned as a pre-formatted string (not float/int) so pandas doesn't
    upcast a mixed int/float column to all-float for CSV output, which would
    turn "0" back into "0.0".
    """
    f = float(raw)
    return str(int(f)) if f == int(f) else str(f)


# ============================================================================
# EXTRACT ONE PDF
# ============================================================================
def extract_one_pdf(pdf_path: Path) -> list[dict]:
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        raw_text = page.extract_text() or ""
        words = page.extract_words(
            x_tolerance=1,
            y_tolerance=3,
            keep_blank_chars=False,
        )

    effective_date = extract_effective_date(raw_text)
    if effective_date is None:
        raise ValueError(f"Could not find Effective Date in {pdf_path.name}")
    print(f"  Effective Date = {effective_date}")

    left_values = extract_left_side_values(words)
    lines = [normalize_decimal_spacing(ln) for ln in raw_text.splitlines()]
    right_start = system_composite_start(lines)

    records: list[dict] = []

    for line_id, name in LEFT_SIDE_COMPONENTS.items():
        raw_val = left_values.get(line_id)
        if raw_val is None:
            print(f"  WARNING: no value found for line {line_id} ({name})")
            continue
        records.append({"date": effective_date, "component": name, "value": clean_value(raw_val)})

    for line_id, name in RIGHT_SIDE_COMPONENTS.items():
        raw_val = find_value_for_right_line(line_id, lines, start=right_start)
        if raw_val is None:
            print(f"  WARNING: no value found for line {line_id} ({name})")
            continue
        records.append({"date": effective_date, "component": name, "value": clean_value(raw_val)})

    return records


# ============================================================================
# MAIN
# ============================================================================
def main():
    pdf_paths = sorted(BASE_DIR.glob("*.pdf"))
    if not pdf_paths:
        raise SystemExit(f"No PDF files found in: {BASE_DIR}")

    all_records: list[dict] = []
    for pdf_path in pdf_paths:
        print(f"\nProcessing: {pdf_path.name}")
        all_records.extend(extract_one_pdf(pdf_path))

    df = pd.DataFrame(all_records, columns=["date", "component", "value"])
    df = df.sort_values(["date", "component"]).reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(FINAL_CSV, index=False)
    print(f"\nSaved {len(df)} records to {FINAL_CSV}")


if __name__ == "__main__":
    main()
