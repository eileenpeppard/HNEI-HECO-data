"""
get_purchased_composite_oahu.py

Extracts the composite purchased-energy price summary from HECO ECRC
purchased_component filings: fossil price (line 87c), renewable price
(line 87d), blended composite price (line 88), and the % of system load
met by purchased energy (line 89).

The "renewable/fossil_price" column records how the fossil/renewable
composite prices were derived. Every filing on hand prints lines 87c/87d
directly, so this script always reports "reported"; older filings that
predate those lines required computing the composite price from other line
items by hand and would have been marked "calculated" instead.

Usage:
    python 4.3_get_purchased_composite_oahu.py
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
FINAL_CSV = OUTPUT_DIR / "purchased_composite.csv"

# Every filing processed by this script prints lines 87c/87d directly.
PRICE_SOURCE = "reported"

# -------------------------------------------------
# LINE IDS (left column, spatial extraction)
# -------------------------------------------------
LINE_FOSSIL = "87c"
LINE_RENEWABLE = "87d"
LINE_COMPOSITE = "88"
LINE_MIX_PCT = "89"
LEFT_SIDE_IDS = {LINE_FOSSIL, LINE_RENEWABLE, LINE_COMPOSITE, LINE_MIX_PCT}

# -------------------------------------------------
# REGEX HELPERS (mirrors 4.2_get_purchased_cost_components_oahu.py)
# -------------------------------------------------
float_pattern = re.compile(r'^[+-]?\d+\.\d+$')
line_id_pattern = re.compile(r'^\d+(\.\d+)?[A-Za-z]?$')


def mid_y(w):
    return (w["top"] + w["bottom"]) / 2.0


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
        if line_id in LEFT_SIDE_IDS:
            values[line_id] = vw["text"]

    return values


def clean_value(raw: str) -> str:
    """Drop insignificant trailing zeros; render whole numbers without a decimal."""
    f = float(raw)
    return str(int(f)) if f == int(f) else str(f)


# ============================================================================
# EXTRACT ONE PDF
# ============================================================================
def extract_one_pdf(pdf_path: Path) -> dict:
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

    values = extract_left_side_values(words)
    missing = LEFT_SIDE_IDS - values.keys()
    if missing:
        raise ValueError(f"{pdf_path.name}: missing line(s) {sorted(missing)}")

    dt = datetime.strptime(effective_date, "%Y-%m-%d")

    return {
        "month": dt.strftime("%Y_%m"),
        "purchased_price_cents_per_kwh_fossil": clean_value(values[LINE_FOSSIL]),
        "purchased_price_cents_per_kwh_renewable": clean_value(values[LINE_RENEWABLE]),
        "purchased_price_cents_per_kwh_composite": clean_value(values[LINE_COMPOSITE]),
        "date": effective_date,
        "purchased_input_into_system_mix_%": clean_value(values[LINE_MIX_PCT]),
        "renewable/fossil_price": PRICE_SOURCE,
    }


# ============================================================================
# MAIN
# ============================================================================
def main():
    pdf_paths = sorted(BASE_DIR.glob("*.pdf"))
    if not pdf_paths:
        raise SystemExit(f"No PDF files found in: {BASE_DIR}")

    records = []
    for pdf_path in pdf_paths:
        print(f"\nProcessing: {pdf_path.name}")
        records.append(extract_one_pdf(pdf_path))

    columns = [
        "month",
        "purchased_price_cents_per_kwh_fossil",
        "purchased_price_cents_per_kwh_renewable",
        "purchased_price_cents_per_kwh_composite",
        "date",
        "purchased_input_into_system_mix_%",
        "renewable/fossil_price",
    ]
    df = pd.DataFrame(records, columns=columns)
    df = df.sort_values("date").reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(FINAL_CSV, index=False)
    print(f"\nSaved {len(df)} records to {FINAL_CSV}")


if __name__ == "__main__":
    main()
