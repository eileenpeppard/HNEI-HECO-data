"""
Extract rate and charge data from HELCO (Big Island) residential bill PDFs
and append rows to a CSV output file.

Reads all *_res_bill.pdf files from INPUT_FOLDER,
extracts the new (later) date's data, and appends to OUTPUT_FILE.
If OUTPUT_FILE does not exist, it is created fresh with a header row.

v14 changes vs v13:
- Rebuilt for HELCO (Big Island) PDF format, which differs from HECO (Oahu):
    * Energy tiers: First 300 kWh / Next 700 kWh  (not 350/850)
    * No DRAC row
    * Row order matches HELCO Attachment 9 layout
    * Charges correctly extracted from 500 kWh and 600 kWh tables
    * Avg Residential Bill totals now captured

Requirements:
    pip install pdfplumber

Usage:
    python big_island_2_extract_res_bill_data_v14.py
"""

import csv
import re
from pathlib import Path
from datetime import datetime
import pdfplumber

# ── Configuration ─────────────────────────────────────────────────────────────
INPUT_FOLDER = r"C:\Users\EileenPeppard\Documents\03_hnei_data_processing\big_island\ecrc\page14_res_bill"
OUTPUT_FILE  = r"C:\Users\EileenPeppard\Documents\03_hnei_data_processing\big_island\ecrc\page14_res_bill\res_bill_history.csv"
# ─────────────────────────────────────────────────────────────────────────────

HEADER_ROW = ['date', 'metric', 'rate', 'charge$_@500kwh', 'charge$_@600kwh', 'bill_order']

# HELCO-specific metric definitions (15 rows, no DRAC).
# Tuple: (metric_key, bill_order, has_rate, rate_list_index, charge_list_index)
#
# Rate list index: position in the numeric values extracted from the Rate panel
#   (after stripping the effective-date string and non-numeric tokens).
#   Order in PDF: base_fuel, first300, next700, customer, interim, rba,
#                 purchased_power, pbf, dsm, solarsaver, ecr, gif  → 12 values
#
# Charge list index: position in the flat numeric list extracted from the
#   500/600 kWh charge tables.
#   Order in PDF: base_fuel, non_fuel_subtotal, first300, next700, customer,
#                 total_base, interim, rba, purchased_power, pbf, dsm,
#                 solarsaver, ecr, gif, avg_bill  → 15 values
METRICS = [
    ("base_fuel/energy_charge_cents/kwh",              1,  True,  0,  0),
    ("non_fuel_energy_charge_subtotal_$",              2,  False, None, 1),
    ("non_fuel_energy_charge_first_300kwh_cents/kwh",  3,  True,  1,  2),
    ("non_fuel_energy_charge_next_700kwh_cents/kwh",   4,  True,  2,  3),
    ("customer_charge_$",                              5,  True,  3,  4),
    ("total_base_charges_$",                           6,  False, None, 5),
    ("interim_rate_adjustment_2019ty_%_on_base",       7,  True,  4,  6),
    ("rba_rate_adjustment_%_except_ecrc",              8,  True,  5,  7),
    ("purchased_power_adj_clause_cents/kwh",           9,  True,  6,  8),
    ("pbf_surcharge_cents/kwh",                       10,  True,  7,  9),
    ("dsm_adjustment_cents/kwh",                      11,  True,  8, 10),
    ("solarsaver_adjustment_cents/kwh",               12,  True,  9, 11),
    ("energy_cost_recovery_cents/kwh",                13,  True, 10, 12),
    ("green_infrastructure_fee_$",                    14,  True, 11, 13),
    ("avg_res_bill_$",                                15,  False, None, 14),
]

N_METRICS = len(METRICS)


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
            continue  # skip date tokens like 11/01/2020
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
        for fmt in ('%m/%d/%Y', '%m/%d/%y'):
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

    The page contains 4 tables:
      Table 0 / Table 2  — Rate panel (3 rows: header | date-row | value-row)
                           col[2] = new rates, newline-separated
      Table 1            — Charge ($) at 500 kWh
      Table 3            — Charge ($) at 600 kWh

    Each charge table:
      row[0]  header ('Charge ($) at 500 Kwh' / '600 Kwh')
      row[1]  date columns
      row[2]  first block of charge values, col[1] = new charges
      row[3]  second block of charge values, col[1] = new charges
      row[4]  avg bill total, col[1] = new total

    Returns dict with keys: date, rates, charges_500, charges_600
    Each list has length N_METRICS (15), indexed by charge_list_index.
    Rates list has 12 entries (rate-bearing rows only).
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

    # ── Date: take the latest date from the 500-table header row ─────────────
    new_date = None
    if table_500 and len(table_500) > 1:
        for cell in table_500[1]:
            d = parse_date(cell)
            if d and (new_date is None or d > new_date):
                new_date = d

    # ── Rates: from rate-panel row[2], col[2] (new/current rates) ────────────
    rates_raw = []
    if table_rate and len(table_rate) > 2:
        cell = table_rate[2][2] if len(table_rate[2]) > 2 else ''
        rates_raw = nums_from_text(cell)

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
        'rates_raw':   rates_raw,       # 12 floats, rate-panel order
        'charges_500': charges_500,     # 15 floats, charge-table order
        'charges_600': charges_600,     # 15 floats, charge-table order
    }


# ── Build data rows ───────────────────────────────────────────────────────────

def build_rows(parsed):
    """Map parsed lists to METRICS and return list of row dicts."""
    date_str    = parsed['date'].strftime('%m/%d/%Y') if parsed['date'] else ''
    rates_raw   = parsed['rates_raw']
    charges_500 = parsed['charges_500']
    charges_600 = parsed['charges_600']

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
    append_to_csv(all_rows)
    print(f"\nDone! {len(all_rows)} rows appended to:\n  {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
