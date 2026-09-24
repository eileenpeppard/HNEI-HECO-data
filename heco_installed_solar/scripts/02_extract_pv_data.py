"""
02_extract_pv_data.py

Reads every quarterly PV summary PDF in input\\ (named like
2026_2Q_pv_summary.pdf by 01_rename_pdfs.py) and pulls the per-utility table
into one long CSV in output\\, one row per utility per quarter:

    date,utility,num_systems,pct_systems_residential,pct_systems_commercial,
    capacity_mw,pct_capacity_residential,pct_capacity_commercial

- date is the quarter-end "as of" date, taken from the filename rather than
  the PDF title, because the title wording changes over the years
  ("3rd Quarter 2012 (as of Sept. 30)", "As of Dec 31, 2025", ...).
- utility is a short code: heco, helco, meco.
- Percentages are whole numbers as printed (97, not 0.97). The earliest
  report (2012 Q3) has no percentage columns, so those cells are blank.
- The printed Total row is not written out; it is used to check that the
  three utility rows were read correctly.

Requires: pip install pdfplumber
"""

import csv
import re
from datetime import date
from pathlib import Path

import pdfplumber


# ── Base path -------------------------------------------------------------
# The data folders live one level up from this script (in scripts\), in the
# heco_installed_solar\ parent folder.
BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_CSV = OUTPUT_DIR / "heco_installed_pv.csv"

CSV_HEADER = [
    "date",
    "utility",
    "num_systems",
    "pct_systems_residential",
    "pct_systems_commercial",
    "capacity_mw",
    "pct_capacity_residential",
    "pct_capacity_commercial",
]

FILENAME_PATTERN = re.compile(r"^(?P<year>\d{4})_(?P<quarter>[1-4])Q_pv_summary\.pdf$")

QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}

# Row labels as they appear in the PDFs -> utility code. The abbreviations
# were used in the 2012 reports, the full names after that.
UTILITY_LABELS = {
    "Hawaiian Electric": "heco",
    "HECO": "heco",
    "Hawai'i Electric Light": "helco",
    "Hawaii Electric Light": "helco",
    "HELCO": "helco",
    "Maui Electric": "meco",
    "MECO": "meco",
}

NUM = r"[\d,]+(?:\.\d+)?"
PCT = r"(\d+)%"

# A utility row: label, number of systems, optional % res / % comm,
# capacity, optional % res / % comm.
ROW_PATTERN = re.compile(
    rf"^(?P<label>{'|'.join(re.escape(k) for k in UTILITY_LABELS)})\s+"
    rf"(?P<num>{NUM})\s+"
    rf"(?:{PCT}\s+{PCT}\s+)?"
    rf"(?P<cap>{NUM})"
    rf"(?:\s+{PCT}\s+{PCT})?\s*$"
)

TOTAL_PATTERN = re.compile(rf"^Total\s+(?P<num>{NUM})\s+(?P<cap>{NUM})\s*$")


# ── Helpers -----------------------------------------------------------------

def to_number(text: str) -> float:
    """'1,144' -> 1144.0"""
    return float(text.replace(",", ""))


def fmt(value: float) -> str:
    """Write whole numbers without a trailing .0 (1144, but 24.3)."""
    return str(int(value)) if value == int(value) else str(value)


def quarter_end_date(year: int, quarter: int) -> date:
    month, day = QUARTER_END[quarter]
    return date(year, month, day)


def normalize_quotes(text: str) -> str:
    """Curly apostrophes/dashes vary between years; make them plain ASCII."""
    return text.replace("’", "'").replace("‘", "'").replace("‐", "-")


def text_lines(page) -> list[str]:
    """
    Page text as lines. Some PDFs (e.g. 2025 Q4) put the row labels and the
    numbers in separate text blocks, so plain extract_text() splits a row
    across lines. Grouping words by their vertical position rebuilds each
    visual row regardless of how the PDF stores it.
    """
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    rows: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if rows and abs(rows[-1][0]["top"] - word["top"]) < 3:
            rows[-1].append(word)
        else:
            rows.append([word])
    return [
        normalize_quotes(" ".join(w["text"] for w in sorted(row, key=lambda w: w["x0"])))
        for row in rows
    ]


def parse_pdf(pdf_path: Path) -> tuple[list[dict], dict | None]:
    """Return (utility rows, total row) parsed from the first page."""
    with pdfplumber.open(pdf_path) as pdf:
        lines = text_lines(pdf.pages[0])

    rows = []
    total = None
    for line in lines:
        if match := ROW_PATTERN.match(line):
            groups = match.groups()
            # groups: label, num, sys_res, sys_comm, cap, cap_res, cap_comm
            rows.append({
                "utility": UTILITY_LABELS[match["label"]],
                "num_systems": to_number(match["num"]),
                "pct_systems_residential": groups[2],
                "pct_systems_commercial": groups[3],
                "capacity_mw": to_number(match["cap"]),
                "pct_capacity_residential": groups[5],
                "pct_capacity_commercial": groups[6],
            })
        elif match := TOTAL_PATTERN.match(line):
            total = {"num_systems": to_number(match["num"]),
                     "capacity_mw": to_number(match["cap"])}
    return rows, total


def check_rows(rows: list[dict], total: dict | None) -> list[str]:
    """Return a list of problems found in one report's rows."""
    problems = []
    codes = sorted(r["utility"] for r in rows)
    if codes != ["heco", "helco", "meco"]:
        problems.append(f"expected heco/helco/meco rows, found {codes}")
        return problems
    if total is None:
        problems.append("no Total row found")
        return problems

    num_sum = sum(r["num_systems"] for r in rows)
    if num_sum != total["num_systems"]:
        problems.append(f"system counts sum to {fmt(num_sum)}, Total says {fmt(total['num_systems'])}")

    # Capacity is rounded per row, so allow a small difference.
    cap_sum = sum(r["capacity_mw"] for r in rows)
    if abs(cap_sum - total["capacity_mw"]) > 1.5:
        problems.append(f"capacity sums to {cap_sum:g}, Total says {total['capacity_mw']:g}")
    return problems


# ── Main --------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    records = []
    failed = []
    for pdf_path in sorted(INPUT_DIR.glob("*.pdf")):
        name_match = FILENAME_PATTERN.match(pdf_path.name)
        if not name_match:
            print(f"SKIP  {pdf_path.name}: name not in YYYY_NQ_pv_summary.pdf format")
            continue
        as_of = quarter_end_date(int(name_match["year"]), int(name_match["quarter"]))

        rows, total = parse_pdf(pdf_path)
        problems = check_rows(rows, total)
        if problems:
            print(f"FAIL  {pdf_path.name}: {'; '.join(problems)}")
            failed.append(pdf_path.name)
            continue

        for row in sorted(rows, key=lambda r: r["utility"]):
            records.append({
                "date": as_of.isoformat(),
                "utility": row["utility"],
                "num_systems": fmt(row["num_systems"]),
                "pct_systems_residential": row["pct_systems_residential"] or "",
                "pct_systems_commercial": row["pct_systems_commercial"] or "",
                "capacity_mw": fmt(row["capacity_mw"]),
                "pct_capacity_residential": row["pct_capacity_residential"] or "",
                "pct_capacity_commercial": row["pct_capacity_commercial"] or "",
            })
        print(f"OK    {pdf_path.name}")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()
        writer.writerows(records)

    print(f"\nWrote {len(records)} rows to {OUTPUT_CSV}")
    if failed:
        print(f"{len(failed)} file(s) failed and were left out: {', '.join(failed)}")


if __name__ == "__main__":
    main()
