"""
purchased_pipeline.py

End-to-end pipeline for HECO ECRC "purchased energy component" filings.
Replaces the old purchased_1 / purchased_2 / purchased_3 scripts with a
single run:

  1. extract_all()  - parse each purchased_component PDF into a per-filing
                       DataFrame (Line, PURCHASED ENERGY COMPONENT, <date>).
  2. combine()       - merge all per-filing DataFrames into one wide table
                       (one column per effective date).
  3. process()       - reshape to long format (price + % of purchased per
                       ERC per date), join, and clean.

Usage:
    python purchased_pipeline.py                  # run all steps
    python purchased_pipeline.py --no-intermediate # skip writing per-stage debug CSVs

Intermediate CSVs (one per PDF, plus the combined wide table) are written to
csv_output/_intermediate/ for debugging a specific filing or date column.
The final result is always csv_output/purchased_energy.csv.
"""

import argparse
import re
import statistics
from datetime import datetime
from collections import defaultdict
from pathlib import Path

import pdfplumber
import pandas as pd

# -------------------------------------------------
# PATHS
# -------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent / "purchased_component"
TEMPLATE_FILE = BASE_DIR / "template_purchased.csv"
ERC_LIST_CSV = BASE_DIR / "erc_list.csv"
OUTPUT_DIR = BASE_DIR / "csv_output"
INTERMEDIATE_DIR = OUTPUT_DIR / "_intermediate"
FINAL_CSV = OUTPUT_DIR / "purchased_energy.csv"

# -------------------------------------------------
# LEFT SIDE LINES (48-100) - spatial extraction
# -------------------------------------------------
LEFT_SIDE_LINES = {
    # Fossil + Renewable Prices
    "48", "49", "50", "51", "52", "53",
    "54", "55", "56", "57", "58", "59", "60", "61", "62", "63",
    "64", "65", "66", "67", "67.1", "67.2", "67.3", "67.4", "67.5", "67.6",

    # MIX % LEFT SIDE
    "68", "69", "70", "71", "72", "73", "73a",
    "74", "75", "76", "77", "78", "79", "80", "81", "82", "83", "84", "85", "86",
    "87", "87.1", "87.2", "87.3", "87.4", "87.5", "87.6", "87a", "87b", "87c", "87d",

    # Composite calc left side
    "88", "89", "90", "91", "92", "93", "94", "95", "96", "97", "98", "99", "100",
}

# -------------------------------------------------
# RIGHT SIDE LINES (124-138) - text-scanning extraction
# -------------------------------------------------
RIGHT_SIDE_LINES = {
    "124", "125", "126", "127", "128", "129", "130", "131",
    "132", "133", "134", "135", "136", "137", "138",
}

# Price / percentage line groupings used in the final reshape (from old step 3)
PRICE_LINES = [
    "48", "49", "50", "51", "52", "53", "54", "55", "56", "57", "58", "59",
    "60", "61", "62", "63", "64", "65", "66", "67", "67.1", "67.2", "67.3",
    "67.4", "67.5", "67.6",
]
PCT_LINES = [
    "68", "69", "70", "71", "72", "73", "73a", "74", "75", "76", "77", "78",
    "79", "80", "81", "82", "83", "84", "85", "86", "87", "87.1", "87.2",
    "87.3", "87.4", "87.5", "87.6", "87a", "87b",
]

# -------------------------------------------------
# REGEX HELPERS
# -------------------------------------------------
float_pattern = re.compile(r'^[+-]?\d+\.\d+$')
five_decimal_pattern = re.compile(r'^\d+\.\d{5}$')   # Special for line 90
line_id_pattern = re.compile(r'^\d+(\.\d+)?[A-Za-z]?$')

# Right-side decimal finder (decimal only, negative via parentheses, optional %)
decimal_pattern = re.compile(r'\(?\s*(-?\d+\.\d+)\s*\)?%?')


def mid_y(w):
    return (w["top"] + w["bottom"]) / 2.0


def find_value_for_right_line(line_id: str, lines: list[str]) -> str | None:
    """
    Handles cases where right-side line numbers appear on the same physical
    line as left-side content.

    Example: "92 WTD CMP... 6.84373 126 ECR Reconciliation Adjustment (0.0450)"
             Here line 126's value is (0.0450) which becomes -0.0450
    """
    target = line_id.strip()

    for i, ln in enumerate(lines):
        pattern = rf'\b{re.escape(target)}\b'

        if re.search(pattern, ln):
            # Line 129's value (17.782) is on the NEXT line, which contains
            # "(lines 124 + 125 + 126 + 127 + 128)"
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


def extract_effective_date(text: str) -> str:
    """
    Extracts:  'Effective Date  - September 1, 2025'
    Returns:   '2025-09-01'
    """
    pat = re.compile(
        r"Effective\s+Date\s*-\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        re.IGNORECASE,
    )
    m = pat.search(text)
    if not m:
        return "Unknown_Date"

    raw = m.group(1).strip()
    try:
        dt = datetime.strptime(raw, "%B %d, %Y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return "Unknown_Date"


# ============================================================================
# STEP 1: EXTRACT (one DataFrame per PDF)
# ============================================================================
def extract_one_pdf(
    pdf_path: Path,
    df_template_master: pd.DataFrame,
    template_line_ids: set[str],
) -> pd.DataFrame:
    """Parse a single purchased_component PDF into a template-shaped DataFrame."""
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        raw_text = page.extract_text() or ""
        words = page.extract_words(
            x_tolerance=1,
            y_tolerance=3,
            keep_blank_chars=False,
        )

    effective_date = extract_effective_date(raw_text)
    print(f"  Effective Date = {effective_date}")
    date_col = effective_date

    # -----------------------------
    # LEFT-SIDE SPATIAL EXTRACTION (48-100)
    # -----------------------------
    values_by_id_left: dict[str, list[str]] = defaultdict(list)

    decimal_words = [w for w in words if float_pattern.match(w["text"])]
    xs_values = [w["x0"] for w in decimal_words if w["x0"] > 100]

    if not xs_values:
        print("  No left-side decimals found; skipping left-side extraction.")
    else:
        left_xs = [x for x in xs_values if x < 400]
        if not left_xs:
            print("  Left numeric column not found; skipping left-side extraction.")
        else:
            left_val_x = statistics.mean(left_xs)
            tolerance_x = 20

            id_words = [
                w for w in words
                if 60 <= w["x0"] <= 100 and line_id_pattern.match(w["text"])
            ]

            if not id_words:
                print("  No left-line IDs found.")
            else:
                for vw in decimal_words:
                    if abs(vw["x0"] - left_val_x) > tolerance_x:
                        continue

                    yv = mid_y(vw)
                    closest_id_word = min(id_words, key=lambda iw: abs(mid_y(iw) - yv))
                    line_id = closest_id_word["text"]
                    text_val = vw["text"]

                    # Special rule for line 90: 5-decimal value between 89 and 91
                    if five_decimal_pattern.match(text_val):
                        if line_id in ["89", "91"]:
                            line_id = "90"

                    if line_id in template_line_ids:
                        values_by_id_left[line_id].append(text_val)

    # -----------------------------
    # RIGHT-SIDE TEXT LINES (124-138)
    # -----------------------------
    lines = raw_text.splitlines()

    # -----------------------------
    # BUILD OUTPUT DATAFRAME
    # -----------------------------
    df_out = df_template_master.copy()

    if "Data" in df_out.columns:
        df_out = df_out.rename(columns={"Data": date_col})
    else:
        raise RuntimeError("Template missing 'Data' column.")

    if effective_date not in ("Unknown_Date", ""):
        df_out.at[0, date_col] = effective_date

    for idx, row in df_out.iterrows():
        line_raw = row["Line"]
        if pd.isna(line_raw):
            continue

        line_id = str(line_raw).strip()
        if not line_id:
            continue

        existing = row[date_col]
        if isinstance(existing, str) and existing.strip() not in ("", "nan", "NaN"):
            continue
        if pd.isna(existing) is False and not isinstance(existing, str):
            continue

        if line_id in LEFT_SIDE_LINES:
            vals = values_by_id_left.get(line_id, [])
            if vals:
                df_out.at[idx, date_col] = vals[-1]
                continue

        if line_id in RIGHT_SIDE_LINES:
            val_r = find_value_for_right_line(line_id, lines)
            if val_r is not None:
                df_out.at[idx, date_col] = val_r
                continue

    return df_out


def extract_all(pdf_folder: Path, keep_intermediate: bool) -> dict[str, pd.DataFrame]:
    """Extract every purchased_component PDF in pdf_folder into DataFrames."""
    df_template_master = pd.read_csv(TEMPLATE_FILE, dtype=str, encoding="cp1252")
    df_template_master = df_template_master.replace("NULL", pd.NA)
    template_line_ids = {
        str(x).strip() for x in df_template_master["Line"].dropna().tolist()
    }

    pdf_names = sorted(
        f.name for f in pdf_folder.glob("*.pdf")
        if "purchased_component" in f.name.lower()
    )

    dfs: dict[str, pd.DataFrame] = {}
    for pdf_name in pdf_names:
        pdf_path = pdf_folder / pdf_name
        print(f"\nProcessing: {pdf_name}")
        df_out = extract_one_pdf(pdf_path, df_template_master, template_line_ids)

        base = Path(pdf_name).stem
        dfs[base] = df_out

        if keep_intermediate:
            INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
            out_path = INTERMEDIATE_DIR / f"purchased_{base}.csv"
            df_out.to_csv(out_path, index=False, encoding="cp1252")
            print(f"  Saved intermediate: {out_path}")

    return dfs


# ============================================================================
# STEP 2: COMBINE (wide table, one column per effective date)
# ============================================================================
def combine(dfs: dict[str, pd.DataFrame], keep_intermediate: bool) -> pd.DataFrame:
    print("\n" + "=" * 80)
    print("COMBINING EXTRACTED FILINGS")
    print("=" * 80)

    if not dfs:
        raise RuntimeError("No extracted filings to combine.")

    bases = sorted(dfs.keys())
    df_combined = dfs[bases[0]].copy()
    print(f"Loaded base structure from: {bases[0]}")

    for base in bases[1:]:
        df_temp = dfs[base]
        date_cols = [c for c in df_temp.columns if c not in ("Line", "PURCHASED ENERGY COMPONENT")]
        if date_cols:
            date_col = date_cols[0]
            df_combined[date_col] = df_temp[date_col]
            print(f"Added data from: {base} (column: {date_col})")
        else:
            print(f"Skipped {base}: no date column found")

    structure_cols = ["Line", "PURCHASED ENERGY COMPONENT"]
    date_cols = [c for c in df_combined.columns if c not in structure_cols]

    try:
        date_cols_sorted = sorted(date_cols, key=lambda x: datetime.strptime(x, "%Y-%m-%d"))
        df_combined = df_combined[structure_cols + date_cols_sorted]
        print(f"Sorted {len(date_cols_sorted)} date columns chronologically")
    except Exception:
        print("Could not sort date columns chronologically, keeping original order")

    if keep_intermediate:
        INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
        combined_path = INTERMEDIATE_DIR / "combined_purchased_data.csv"
        df_combined.to_csv(combined_path, index=False, encoding="cp1252")
        print(f"Saved intermediate: {combined_path}")

    print(f"Combined dimensions: {df_combined.shape[0]} rows x {df_combined.shape[1]} columns")
    return df_combined


# ============================================================================
# STEP 3: PROCESS (reshape to long format, join, clean)
# ============================================================================
def process(df: pd.DataFrame) -> pd.DataFrame:
    print("\n" + "=" * 80)
    print("PROCESSING PURCHASED ENERGY DATA")
    print("=" * 80)

    date_columns = [c for c in df.columns if c not in ("Line", "PURCHASED ENERGY COMPONENT")]
    print(f"Found {len(date_columns)} date columns")

    # ---- Price data (Lines 48-67.6) ----
    df_price = df[df["Line"].astype(str).isin(PRICE_LINES)].copy()
    df_price_long = df_price.melt(
        id_vars=["Line", "PURCHASED ENERGY COMPONENT"],
        value_vars=date_columns,
        var_name="date",
        value_name="price_cents_per_kwh",
    )
    df_price_long = df_price_long.rename(columns={"PURCHASED ENERGY COMPONENT": "erc_name"})
    df_price_long = df_price_long[["date", "erc_name", "price_cents_per_kwh"]]
    df_price_long = df_price_long.dropna(subset=["price_cents_per_kwh"])
    df_price_long = df_price_long[
        (df_price_long["price_cents_per_kwh"].astype(str).str.strip() != "")
        & (df_price_long["price_cents_per_kwh"].astype(str).str.upper() != "NULL")
        & (df_price_long["price_cents_per_kwh"].astype(str).str.upper() != "NAN")
    ]
    print(f"Price data reshaped to long format: {len(df_price_long)} records")

    # ---- Percentage data (Lines 68-87.6) ----
    df_pct = df[df["Line"].astype(str).isin(PCT_LINES)].copy()
    df_pct_long = df_pct.melt(
        id_vars=["Line", "PURCHASED ENERGY COMPONENT"],
        value_vars=date_columns,
        var_name="date",
        value_name="%_of_purchased",
    )
    df_pct_long = df_pct_long.rename(columns={"PURCHASED ENERGY COMPONENT": "erc_name"})
    df_pct_long = df_pct_long[["date", "erc_name", "%_of_purchased"]]
    df_pct_long = df_pct_long.dropna(subset=["%_of_purchased"])
    df_pct_long = df_pct_long[
        (df_pct_long["%_of_purchased"].astype(str).str.strip() != "")
        & (df_pct_long["%_of_purchased"].astype(str).str.upper() != "NULL")
        & (df_pct_long["%_of_purchased"].astype(str).str.upper() != "NAN")
    ]
    print(f"Percentage data reshaped to long format: {len(df_pct_long)} records")

    # ---- Join ----
    df_final = pd.merge(df_price_long, df_pct_long, on=["erc_name", "date"], how="inner")
    df_final = df_final[["erc_name", "date", "price_cents_per_kwh", "%_of_purchased"]]
    df_final = df_final.sort_values(["date", "erc_name"]).reset_index(drop=True)
    print(f"Joined data: {len(df_final)} records")

    # ---- Clean up: drop 'Unused' rows that are all zero ----
    df_final["price_cents_per_kwh"] = pd.to_numeric(df_final["price_cents_per_kwh"], errors="coerce")
    df_final["%_of_purchased"] = pd.to_numeric(df_final["%_of_purchased"], errors="coerce")

    rows_before = len(df_final)
    df_final = df_final[
        ~(
            (df_final["erc_name"].str.strip().str.upper() == "UNUSED")
            & (df_final["price_cents_per_kwh"] == 0)
            & (df_final["%_of_purchased"] == 0)
        )
    ]
    print(f"Removed {rows_before - len(df_final)} 'Unused' rows with zero values")

    return df_final


def compare_with_erc_list(df_final: pd.DataFrame) -> None:
    print("\n" + "=" * 80)
    print("COMPARING ERC NAMES WITH REFERENCE LIST")
    print("=" * 80)

    try:
        df_erc_list = pd.read_csv(ERC_LIST_CSV, encoding="cp1252")
    except FileNotFoundError:
        print(f"ERC list file not found: {ERC_LIST_CSV}")
        return

    print(f"Loaded ERC list: {len(df_erc_list)} reference names")

    names_in_data = set(df_final["erc_name"].str.strip().unique())
    names_in_list = set(df_erc_list["erc_name"].str.strip().unique())

    names_not_in_list = names_in_data - names_in_list
    names_not_in_data = names_in_list - names_in_data

    if names_not_in_list:
        print(f"\nWARNING: {len(names_not_in_list)} names in DATA but NOT in reference list:")
        for name in sorted(names_not_in_list):
            print(f"  - '{name}'")
    else:
        print("\nAll names in data are in the reference list")

    if names_not_in_data:
        print(f"\nINFO: {len(names_not_in_data)} names in REFERENCE LIST but not in data:")
        for name in sorted(names_not_in_data):
            print(f"  - '{name}'")
    else:
        print("\nAll reference names appear in the data")

    if names_in_data == names_in_list:
        print("\nPERFECT MATCH: All names match exactly!")


# ============================================================================
# MAIN
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description="Extract, combine, and process HECO purchased energy filings.")
    parser.add_argument(
        "--no-intermediate",
        action="store_true",
        help="Skip writing per-PDF and combined debug CSVs to csv_output/_intermediate/",
    )
    args = parser.parse_args()
    keep_intermediate = not args.no_intermediate

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dfs = extract_all(BASE_DIR, keep_intermediate)
    df_combined = combine(dfs, keep_intermediate)
    df_final = process(df_combined)

    df_final.to_csv(FINAL_CSV, index=False, encoding="cp1252")
    print(f"\nOutput saved to: {FINAL_CSV}")
    print(f"Final dimensions: {df_final.shape[0]} rows x {df_final.shape[1]} columns")
    print(f"Date range: {df_final['date'].min()} to {df_final['date'].max()}")
    print(f"Unique ERC names: {df_final['erc_name'].nunique()}")

    compare_with_erc_list(df_final)

    print("\n" + "=" * 80)
    print("PIPELINE COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
