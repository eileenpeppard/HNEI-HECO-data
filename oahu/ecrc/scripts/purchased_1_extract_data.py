import os
import re
import statistics
from datetime import datetime
from collections import defaultdict
from pathlib import Path

import pdfplumber
import pandas as pd

# -------------------------------------------------
# PATHS – EDIT THESE IF NEEDED
# -------------------------------------------------
BASE_DIR      = Path(__file__).resolve().parent.parent / "purchased_component"
template_file = BASE_DIR / "template_purchased.csv"
pdf_folder    = BASE_DIR
output_folder = BASE_DIR / "csv_output"

os.makedirs(output_folder, exist_ok=True)

# -------------------------------------------------
# LOAD TEMPLATE
# -------------------------------------------------
df_template_master = pd.read_csv(template_file, dtype=str, encoding="cp1252")
df_template_master = df_template_master.replace("NULL", pd.NA)

template_line_ids = {
    str(x).strip()
    for x in df_template_master["Line"].dropna().tolist()
}

# -------------------------------------------------
# LEFT SIDE LINES (48–100) – spatial extraction
# -------------------------------------------------
LEFT_SIDE_LINES = {
    # Fossil + Renewable Prices
    "48","49","50","51","52","53",
    "54","55","56","57","58","59","60","61","62","63",
    "64","65","66","67","67.1","67.2","67.3","67.4","67.5","67.6",

    # MIX % LEFT SIDE
    "68","69","70","71","72","73","73a",
    "74","75","76","77","78","79","80","81","82","83","84","85","86",
    "87","87.1","87.2","87.3","87.4","87.5","87.6","87a","87b","87c","87d",

    # Composite calc left side
    "88","89","90","91","92","93","94","95","96","97","98","99","100"
}

# -------------------------------------------------
# RIGHT SIDE LINES (124–138) – text-scanning extraction
# -------------------------------------------------
RIGHT_SIDE_LINES = {
    "124","125","126","127","128","129","130","131",
    "132","133","134","135","136","137","138"
}

# -------------------------------------------------
# REGEX HELPERS
# -------------------------------------------------
# plain decimal like 17.776, 6.52405, 0.00000 (no commas, no %)
float_pattern        = re.compile(r'^[+-]?\d+\.\d+$')
five_decimal_pattern = re.compile(r'^\d+\.\d{5}$')   # Special for line 90
line_id_pattern      = re.compile(r'^\d+(\.\d+)?[A-Za-z]?$')

# Right-side decimal finder (decimal only, negative via parentheses, optional %)
# Example matches: "17.6937", "(1.952)", "0.0000", "(0.0450)", "31.983%"
decimal_pattern = re.compile(r'\(?\s*(-?\d+\.\d+)\s*\)?%?')

def mid_y(w):
    return (w["top"] + w["bottom"]) / 2.0

# -------------------------------------------------
# RIGHT SIDE DECIMAL EXTRACTION (FIXED VERSION)
# -------------------------------------------------
def extract_last_decimal(text: str) -> str | None:
    """
    Extract LAST decimal in the line.
    Must contain a decimal → won't grab line numbers.
    Handles parentheses → negative.
    """
    matches = list(decimal_pattern.finditer(text))
    if not matches:
        return None

    full = matches[-1].group(0)
    num  = matches[-1].group(1)

    # Parentheses mean negative
    if full.strip().startswith("(") and full.strip().endswith(")"):
        if not num.startswith("-"):
            num = "-" + num

    return num


def find_value_for_right_line(line_id: str, lines: list[str]) -> str | None:
    """
    FIXED VERSION: Handles cases where right-side line numbers 
    appear on same physical line as left-side content.
    
    Example: "92 WTD CMP... 6.84373 126 ECR Reconciliation Adjustment (0.0450)"
             Here line 126's value is (0.0450) which becomes -0.0450
    """
    target = line_id.strip()
    
    for i, ln in enumerate(lines):
        # Check if this line contains our target line number as a standalone token
        pattern = rf'\b{re.escape(target)}\b'
        
        if re.search(pattern, ln):
            # Special handling for line 129
            # Line 129 is on same line as "94 Base % ... 0.0000 129 Monthly Energy..."
            # Its value (17.782) is on the NEXT line which contains "(lines 124 + 125...)"
            if target == "129":
                for j in range(i + 1, min(i + 4, len(lines))):
                    # Look for the line with "lines 124 + 125 + 126 + 127 + 128"
                    if "lines 124" in lines[j] or "(lines 124" in lines[j]:
                        matches = list(decimal_pattern.finditer(lines[j]))
                        if matches:
                            full = matches[-1].group(0)
                            num = matches[-1].group(1)
                            
                            if full.strip().startswith("(") and full.strip().endswith(")"):
                                if not num.startswith("-"):
                                    num = "-" + num
                            
                            return num
                # If we didn't find it with the special logic, continue with normal logic
            
            # Found the line containing our target line number
            # Try to extract from THIS line first
            matches = list(decimal_pattern.finditer(ln))
            
            if matches:
                # Get the last match
                full = matches[-1].group(0)
                num = matches[-1].group(1)
                
                # Handle parentheses = negative
                if full.strip().startswith("(") and full.strip().endswith(")"):
                    if not num.startswith("-"):
                        num = "-" + num
                
                return num
            
            # If no decimal on this line, check next 3 lines
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

# -------------------------------------------------
# EFFECTIVE DATE
# -------------------------------------------------
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


# -------------------------------------------------
# MAIN EXTRACTION LOOP
# -------------------------------------------------
for pdf_name in sorted(f for f in os.listdir(pdf_folder) if f.lower().endswith(".pdf") and "purchased_component" in f.lower()):
    pdf_path = pdf_folder / pdf_name
    print(f"\n📄 Processing {pdf_name}")

    # Open PDF, get text and words
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        raw_text = page.extract_text() or ""
        words = page.extract_words(
            x_tolerance=1,
            y_tolerance=3,
            keep_blank_chars=False
        )

    # Effective date
    effective_date = extract_effective_date(raw_text)
    print(f"  🗓 Effective Date = {effective_date}")
    date_col = effective_date

    # -----------------------------
    # LEFT-SIDE SPATIAL EXTRACTION (48–100)
    # -----------------------------
    values_by_id_left: dict[str, list[str]] = defaultdict(list)

    # decimal words like 17.776, 13.541, 6.52405 (no commas, no %)
    decimal_words = [w for w in words if float_pattern.match(w["text"])]

    xs_values = [w["x0"] for w in decimal_words if w["x0"] > 100]

    if not xs_values:
        print("  ⚠ No left-side decimals found; skipping left-side extraction.")
    else:
        # numeric column is left side: x ~ 270–280, < 400 is safe
        left_xs = [x for x in xs_values if x < 400]
        if not left_xs:
            print("  ⚠ Left numeric column not found; skipping left-side extraction.")
        else:
            left_val_x = statistics.mean(left_xs)
            tolerance_x = 20

            # Line IDs in the left margin (48–100 etc.)
            id_words = [
                w for w in words
                if 60 <= w["x0"] <= 100 and line_id_pattern.match(w["text"])
            ]

            if not id_words:
                print("  ⚠ No left-line IDs found.")
            else:
                for vw in decimal_words:
                    # keep only decimals in the left numeric column
                    if abs(vw["x0"] - left_val_x) > tolerance_x:
                        continue

                    yv = mid_y(vw)
                    closest_id_word = min(
                        id_words,
                        key=lambda iw: abs(mid_y(iw) - yv)
                    )
                    line_id = closest_id_word["text"]
                    text_val = vw["text"]

                    # Special rule for line 90: 5-decimal value between 89 and 91
                    if five_decimal_pattern.match(text_val):
                        if line_id in ["89", "91"]:
                            line_id = "90"

                    # Only keep line IDs that appear in the template
                    if line_id in template_line_ids:
                        values_by_id_left[line_id].append(text_val)

    # -----------------------------
    # RIGHT-SIDE TEXT LINES (124–138)
    # -----------------------------
    lines = raw_text.splitlines()

    # -----------------------------
    # BUILD OUTPUT DATAFRAME
    # -----------------------------
    df_out = df_template_master.copy()

    # Rename "Data" -> effective_date column
    if "Data" in df_out.columns:
        df_out = df_out.rename(columns={"Data": date_col})
    else:
        # If template got changed, we bail with a message
        raise RuntimeError("Template missing 'Data' column.")

    # Put effective date into row 0 if available
    if effective_date not in ("Unknown_Date", ""):
        df_out.at[0, date_col] = effective_date

    # Fill rows from left and right logic
    for idx, row in df_out.iterrows():
        line_raw = row["Line"]
        if pd.isna(line_raw):
            continue

        line_id = str(line_raw).strip()
        if not line_id:
            continue

        # Skip if value already present (template or previous processing)
        existing = row[date_col]
        if isinstance(existing, str) and existing.strip() not in ("", "nan", "NaN"):
            continue
        if pd.isna(existing) is False and not isinstance(existing, str):
            # some non-string non-NA value is there, skip
            continue

        # ---- LEFT SIDE LINES (48–100) ----
        if line_id in LEFT_SIDE_LINES:
            vals = values_by_id_left.get(line_id, [])
            if vals:
                # Use the last value (safest if multiple)
                df_out.at[idx, date_col] = vals[-1]
                continue  # do not overwrite from right-side logic

        # ---- RIGHT SIDE LINES (124–138) ----
        if line_id in RIGHT_SIDE_LINES:
            val_r = find_value_for_right_line(line_id, lines)
            if val_r is not None:
                df_out.at[idx, date_col] = val_r
                continue

    # -----------------------------
    # SAVE OUTPUT
    # -----------------------------
    base = os.path.splitext(pdf_name)[0]
    output_name = f"purchased_{base}.csv"
    output_path = output_folder / output_name
    df_out.to_csv(output_path, index=False, encoding="cp1252")

    print(f"  ✅ Saved: {output_path}")

print("\n" + "=" * 80)
print("✨ ALL FILES PROCESSED!")
print("=" * 80)
