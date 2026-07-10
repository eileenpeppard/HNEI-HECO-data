"""
Extract rate and charge data from HECO (Oahu) residential bill PDFs
and write rows to a CSV output file.

Reads all *_res_bill.pdf files from INPUT_FOLDER, extracts each one's
data, and writes OUTPUT_FILE fresh (overwriting any previous run).

v17 changes vs v16 (both bugs confirmed against real pdfplumber output
on the June and July 2026 filings, not just inferred from text):

1. FIXED table_600 column bug: pdfplumber merges the 600-kWh charge
   table together with a duplicate copy of the rate table when it
   extracts this page, giving columns
       [label, rate_old, rate_new, blank, charge_old, charge_new, diff]
   v16's extract_charges() always read column index 1, which is
   correct for the 500-kWh table (a clean 3-column charge-only table)
   but on the 600-kWh table grabs rate_old instead of the charge. This
   silently produced wrong charge$_@600kwh values for EVERY filing,
   not just this month's.
2. FIXED stale METRICS row order: v16 assumed a "non-fuel energy
   charge subtotal" row with a numeric value (it's actually just a
   section header, no value) and had no entries at all for three rows
   that are present in current filings: "Demand Response Adjustment
   Clause", "Refund of 2011 Interim", and "Renewable Energy
   Infrastructure Cost Recovery Provision". Every index past
   "Customer Charge" was pointing at the wrong row as a result.
3. Renamed the two non-fuel tier metrics from first_300kwh/next_700kwh
   to first_350kwh/next_850kwh to match the tier breakpoints actually
   used in current filings (HECO's tiers changed at some point after
   v16's naming was set) -- rename back if your Postgres schema
   expects the old column/value names.
4. Added a sanity check: each filing is expected to yield exactly 15
   rate values and 17 charge values (per panel). If pdfplumber returns
   a different count -- meaning HECO changed the row layout again --
   the script prints a loud warning instead of silently writing
   misaligned data, which is what let this bug go unnoticed.

Requirements:
    pip install pdfplumber

Usage:
    python get_ecrc_res_bill_data_oahu_v17.py
"""

import csv
import re
from pathlib import Path
from datetime import datetime
import pdfplumber

# ── Configuration ─────────────────────────────────────────────────────────────
INPUT_FOLDER = str(Path(__file__).resolve().parent.parent / "res_bill")
OUTPUT_FILE  = str(Path(__file__).resolve().parent.parent / "res_bill" / "csv_output" / "res_bill_history.csv")
# ─────────────────────────────────────────────────────────────────────────────

HEADER_ROW = ['date', 'metric', 'rate', 'charge$_@500kwh', 'charge$_@600kwh', 'bill_order']

# ── Metric definitions (verified against real pdfplumber output) ─────────────
# Tuple: (metric_key, bill_order, has_rate, rate_idx, charge_idx)
#
# Rates: 15 values in this order (from the rate-only table's row[2][col]):
#   base_fuel, first350, next850, customer, ppa, rba, dsm,
#   demand_response, interim, refund_2011, pbf, reic, solarsaver, ecr, gif
#
# Charges: 17 values in this order (flattened rows 2-4 of the 500-kWh
# table -- there is NO subtotal row, but there IS a total_base_charges
# row and an avg_res_bill row):
#   base_fuel, first350, next850, customer, total_base, ppa, rba, dsm,
#   demand_response, interim, refund_2011, pbf, reic, solarsaver, ecr,
#   gif, avg_res_bill

METRICS = [
    # metric_key                                              order  has_rate  rate_idx  charge_idx
    ("base_fuel/energy_charge_cents/kwh",                   1,  True,   0,   0),
    ("non_fuel_energy_charge_first_350kwh_cents/kwh",       2,  True,   1,   1),
    ("non_fuel_energy_charge_next_850kwh_cents/kwh",        3,  True,   2,   2),
    ("customer_charge_$",                                   4,  True,   3,   3),
    ("total_base_charges_$",                                5,  False, None,   4),
    ("demand_response_adjustment_cents/kwh",                6,  True,   4,   5),
    ("rba_rate_adjustment_%_except_ecrc",                   7,  True,   5,   6),
    ("dsm_adjustment_cents/kwh",                            8,  True,   6,   7),
    ("demand_response_adjustment_cents/kwh",                9,  True,   7,   8),
    ("interim_rate_increase_ty2017_%_on_base",             10,  True,   8,   9),
    ("refund_of_2011_interim_%_on_base",                   11,  True,   9,  10),
    ("pbf_surcharge_cents/kwh",                            12,  True,  10,  11),
    ("renewable_energy_infra_cost_recovery_cents/kwh",     13,  True,  11,  12),
    ("solarsaver_adjustment_cents/kwh",                    14,  True,  12,  13),
    ("energy_cost_recovery_cents/kwh",                     15,  True,  13,  14),
    ("green_infrastructure_fee_$",                         16,  True,  14,  15),
    ("avg_res_bill_$",                                     17,  False, None,  16),
]

EXPECTED_RATE_COUNT   = 15
EXPECTED_CHARGE_COUNT = 17


# ── Helpers ───────────────────────────────────────────────────────────────────

def nums_from_text(text):
    """
    Extract an ordered list of floats from a newline-separated cell string.
    Skips date strings and blank tokens. '-' → 0.0. '(x)' → -x.
    """
    results = []
    for part in str(text).split('\n'):
        part = part.strip().replace('$', '').replace('%', '').replace(',', '').replace(' ', '')
        if part in ('', 'None', 'none'):
            continue
        if re.match(r'\d{1,2}/\d{1,2}/\d{2,4}$', part):
            continue
        if part == '-':
            results.append(0.0)
            continue
        neg = part.startswith('(') and part.endswith(')')
        part = part.strip('()')
        try:
            results.append(-float(part) if neg else float(part))
        except ValueError:
            pass
    return results


def parse_date(cell_text):
    """Return the latest valid date found in a cell string."""
    dates = []
    for tok in str(cell_text).split():
        for fmt in ('%m/%d/%Y', '%m/%d/%y', '%m-%d-%Y', '%m-%d-%y'):
            try:
                d = datetime.strptime(tok.strip(), fmt)
                if d.year >= 2010:
                    dates.append(d)
                break
            except ValueError:
                pass
    return max(dates) if dates else None


# ── PDF parser ────────────────────────────────────────────────────────────────

def parse_pdf(pdf_path):
    """
    Parse one HECO residential bill PDF (Oahu).

    pdfplumber's extract_tables() returns 3 tables for this page layout:
      - a rate-only table (label blob + two rate columns)
      - a clean 500-kWh charge table (3 columns: charge_old, charge_new, diff)
      - a MERGED 600-kWh table that also carries a duplicate rate table
        side-by-side with it (7 columns: label, rate_old, rate_new, blank,
        charge_old, charge_new, diff)

    Returns dict with keys: date, rates_raw, charges_500, charges_600
    """
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        tables = page.extract_tables()

    if not tables:
        raise ValueError(f"No tables found in {pdf_path}")

    table_rate = None
    table_500  = None
    table_600  = None

    for t in tables:
        if not t:
            continue
        header = str(t[0])
        if '500' in header:
            table_500 = t
        elif '600' in header:
            table_600 = t
        elif 'Rate' in header and table_rate is None:
            table_rate = t

    # ── Date: latest date from the 500-table header row ───────────────────────
    bill_date = None
    if table_500 and len(table_500) > 1:
        for cell in table_500[1]:
            d = parse_date(cell)
            if d and (bill_date is None or d > bill_date):
                bill_date = d

    # ── Rates: from the dedicated rate table, current-date column ────────────
    rates_raw = []
    if table_rate and len(table_rate) > 2:
        cell = table_rate[2][2] if len(table_rate[2]) > 2 else ''
        rates_raw = nums_from_text(cell)

    # ── Charges: 500-kWh table is clean (col index 1 = current charge) ───────
    def extract_charges_clean(table, col):
        vals = []
        if not table:
            return vals
        for row in table[2:]:
            cell = row[col] if len(row) > col else None
            if cell:
                vals.extend(nums_from_text(cell))
        return vals

    charges_500 = extract_charges_clean(table_500, col=1)

    # ── 600-kWh table: detect whether it's merged with the rate table ────────
    # Clean (charge-only) layout: 3 columns -> current charge is col 1.
    # Merged layout (rate + charge together): 7 columns -> current charge is col 5.
    charges_600 = []
    if table_600:
        max_cols = max(len(r) for r in table_600)
        charge_col = 1 if max_cols <= 4 else 5
        charges_600 = extract_charges_clean(table_600, col=charge_col)

    return {
        'date':        bill_date,
        'rates_raw':   rates_raw,
        'charges_500': charges_500,
        'charges_600': charges_600,
    }


# ── Build data rows ───────────────────────────────────────────────────────────

def build_rows(parsed, pdf_name=""):
    """Map parsed lists to METRICS using the verified index positions."""
    date_str    = parsed['date'].strftime('%m/%d/%Y') if parsed['date'] else ''
    rates_raw   = parsed['rates_raw']
    charges_500 = parsed['charges_500']
    charges_600 = parsed['charges_600']

    if len(rates_raw) != EXPECTED_RATE_COUNT:
        print(f"  WARNING [{pdf_name}]: expected {EXPECTED_RATE_COUNT} rate values, "
              f"got {len(rates_raw)}. Row layout may have changed -- check METRICS indices "
              f"before trusting this file's output.")
    if len(charges_500) != EXPECTED_CHARGE_COUNT:
        print(f"  WARNING [{pdf_name}]: expected {EXPECTED_CHARGE_COUNT} charge_500 values, "
              f"got {len(charges_500)}.")
    if len(charges_600) != EXPECTED_CHARGE_COUNT:
        print(f"  WARNING [{pdf_name}]: expected {EXPECTED_CHARGE_COUNT} charge_600 values, "
              f"got {len(charges_600)}.")

    rows = []
    for metric, order, has_rate, r_idx, c_idx in METRICS:
        rate = ''
        if has_rate and r_idx is not None and r_idx < len(rates_raw):
            rate = rates_raw[r_idx]

        c500 = charges_500[c_idx] if c_idx is not None and c_idx < len(charges_500) else ''
        c600 = charges_600[c_idx] if c_idx is not None and c_idx < len(charges_600) else ''

        rows.append({
            'date':            date_str,
            'metric':          metric,
            'rate':            rate,
            'charge$_@500kwh': c500,
            'charge$_@600kwh': c600,
            'bill_order':      order,
        })
    return rows


# ── CSV writer ────────────────────────────────────────────────────────────────

def write_csv(all_rows):
    out = Path(OUTPUT_FILE)
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(str(out), 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=HEADER_ROW)
        writer.writeheader()
        writer.writerows(all_rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    folder = Path(INPUT_FOLDER)
    pdfs   = sorted(folder.glob("*_res_bill.pdf"))

    if not pdfs:
        print(f"No *_res_bill.pdf files found in:\n  {INPUT_FOLDER}")
        return

    print(f"Found {len(pdfs)} PDF file(s).\n")
    all_rows = []

    for pdf in pdfs:
        print(f"Processing: {pdf.name}")
        try:
            parsed = parse_pdf(pdf)
            rows   = build_rows(parsed, pdf_name=pdf.name)
            date_s = parsed['date'].strftime('%m/%d/%Y') if parsed['date'] else 'unknown'
            print(f"  Date: {date_s}  |  {len(rows)} rows")
            all_rows.extend(rows)
        except Exception as e:
            import traceback
            print(f"  ERROR: {e}")
            traceback.print_exc()

    if not all_rows:
        print("No data extracted.")
        return

    all_rows.sort(key=lambda r: (r['date'], r['bill_order']))
    write_csv(all_rows)
    print(f"\nDone! {len(all_rows)} rows written to:\n  {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
