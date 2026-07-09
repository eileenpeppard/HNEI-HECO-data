"""
Extract rate and charge data from HECO (Oahu) residential bill PDFs
and append rows to a CSV output file.

Reads all *_res_bill.pdf files from INPUT_FOLDER,
extracts the new (later) date's data, and appends to OUTPUT_FILE.
If OUTPUT_FILE does not exist, it is created fresh with a header row.

v16 changes vs v15:
- Fixed date parsing for older PDFs that use dashes instead of slashes
  (e.g. '1-01-15' and '12-01-14') by adding %m-%d-%y and %m-%d-%Y
  to the parse_date format list.

Requirements:
    pip install pdfplumber

Usage:
    python big_island_2_extract_res_bill_data_v16.py
"""

import csv
import re
from pathlib import Path
from datetime import datetime
import pdfplumber

# ── Configuration ─────────────────────────────────────────────────────────────
INPUT_FOLDER = str(Path(__file__).resolve().parent.parent / "res_bill")
OUTPUT_FILE  = str(Path(__file__).resolve().parent.parent / "res_bill" / "res_bill_history.csv")
# ─────────────────────────────────────────────────────────────────────────────

HEADER_ROW = ['date', 'metric', 'rate', 'charge$_@500kwh', 'charge$_@600kwh', 'bill_order']

# ── Metric definitions ────────────────────────────────────────────────────────
# Tuple: (metric_key, bill_order, has_rate, rate_idx_new, charge_idx_new,
#                                           rate_idx_old, charge_idx_old)
#
# NEW format (>= 2020, 12 rate values, 15 charge values):
#   Rates:   base_fuel, first300, next700, customer, interim, rba,
#            ppa, pbf, dsm, solarsaver, ecr, gif
#   Charges: base_fuel, nonfuel_subtotal, first300, next700, customer,
#            total_base, interim, rba, ppa, pbf, dsm, solarsaver, ecr, gif, avg
#
# OLD format (pre-2020, 11 rate values, 14 charge values — no interim row):
#   Rates:   base_fuel, first300, next700, customer, rba,
#            ppa, pbf, dsm, solarsaver, ecr, gif
#   Charges: base_fuel, nonfuel_subtotal, first300, next700, customer,
#            total_base, rba, ppa, pbf, dsm, solarsaver, ecr, gif, avg
#
# None in rate/charge index means the row doesn't exist in that format.

METRICS = [
    # metric_key                                          order  has_rate  r_new c_new  r_old c_old
    ("base_fuel/energy_charge_cents/kwh",              1,  True,  0,  0,   0,  0),
    ("non_fuel_energy_charge_subtotal_$",              2,  False, None, 1,  None, 1),
    ("non_fuel_energy_charge_first_300kwh_cents/kwh",  3,  True,  1,  2,   1,  2),
    ("non_fuel_energy_charge_next_700kwh_cents/kwh",   4,  True,  2,  3,   2,  3),
    ("customer_charge_$",                              5,  True,  3,  4,   3,  4),
    ("total_base_charges_$",                           6,  False, None, 5,  None, 5),
    ("interim_rate_adjustment_2019ty_%_on_base",       7,  True,  4,  6,   None, None),  # new only
    ("rba_rate_adjustment_%_except_ecrc",              8,  True,  5,  7,   4,  6),
    ("purchased_power_adj_clause_cents/kwh",           9,  True,  6,  8,   5,  7),
    ("pbf_surcharge_cents/kwh",                       10,  True,  7,  9,   6,  8),
    ("dsm_adjustment_cents/kwh",                      11,  True,  8, 10,   7,  9),
    ("solarsaver_adjustment_cents/kwh",               12,  True,  9, 11,   8, 10),
    ("energy_cost_recovery_cents/kwh",                13,  True, 10, 12,   9, 11),
    ("green_infrastructure_fee_$",                    14,  True, 11, 13,  10, 12),
    ("avg_res_bill_$",                                15,  False, None, 14, None, 13),
]

N_METRICS    = len(METRICS)
NEW_RATE_MIN = 12   # >= this many rates → new format


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
        if re.match(r'\d{1,2}/\d{1,2}/\d{4}', part):
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
    Parse one HELCO residential bill PDF.

    Handles two formats:
      NEW (>= ~2020): 12 rate values, 15 charge values — includes Interim row
      OLD (pre-2020): 11 rate values, 14 charge values — no Interim row

    Format is auto-detected from the number of rate values extracted.

    Returns dict with keys: date, new_format, rates_raw, charges_500, charges_600
    """
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        tables = page.extract_tables()

    if not tables:
        raise ValueError(f"No tables found in {pdf_path}")

    # Identify tables by header text
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
    new_date = None
    if table_500 and len(table_500) > 1:
        for cell in table_500[1]:
            d = parse_date(cell)
            if d and (new_date is None or d > new_date):
                new_date = d

    # ── Rates: rate-panel row[2], col[2] (new/current rates) ─────────────────
    rates_raw = []
    if table_rate and len(table_rate) > 2:
        cell = table_rate[2][2] if len(table_rate[2]) > 2 else ''
        rates_raw = nums_from_text(cell)

    # ── Detect format ─────────────────────────────────────────────────────────
    new_format = len(rates_raw) >= NEW_RATE_MIN

    # ── Charges: flatten all data rows (rows 2+) + avg row, col[1] ───────────
    def extract_charges(table):
        vals = []
        if not table:
            return vals
        for row in table[2:]:
            cell = row[1] if len(row) > 1 else None
            if cell:
                vals.extend(nums_from_text(cell))
        return vals

    charges_500 = extract_charges(table_500)
    charges_600 = extract_charges(table_600)

    return {
        'date':        new_date,
        'new_format':  new_format,
        'rates_raw':   rates_raw,
        'charges_500': charges_500,
        'charges_600': charges_600,
    }


# ── Build data rows ───────────────────────────────────────────────────────────

def build_rows(parsed):
    """Map parsed lists to METRICS using the correct format indices."""
    date_str    = parsed['date'].strftime('%m/%d/%Y') if parsed['date'] else ''
    new_format  = parsed['new_format']
    rates_raw   = parsed['rates_raw']
    charges_500 = parsed['charges_500']
    charges_600 = parsed['charges_600']

    rows = []
    for metric, order, has_rate, r_new, c_new, r_old, c_old in METRICS:
        r_idx = r_new if new_format else r_old
        c_idx = c_new if new_format else c_old

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

def append_to_csv(all_rows):
    out = Path(OUTPUT_FILE)
    write_header = not out.exists()

    with open(str(out), 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=HEADER_ROW)
        if write_header:
            writer.writeheader()
            print("  Created new output file with header row.")
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
            rows   = build_rows(parsed)
            date_s = parsed['date'].strftime('%m/%d/%Y') if parsed['date'] else 'unknown'
            fmt    = "new" if parsed['new_format'] else "old (no interim)"
            print(f"  Date: {date_s}  |  Format: {fmt}  |  {len(rows)} rows")
            all_rows.extend(rows)
        except Exception as e:
            import traceback
            print(f"  ERROR: {e}")
            traceback.print_exc()

    if not all_rows:
        print("No data extracted.")
        return

    all_rows.sort(key=lambda r: (r['date'], r['bill_order']))
    append_to_csv(all_rows)
    print(f"\nDone! {len(all_rows)} rows appended to:\n  {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
