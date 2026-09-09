"""
extract_ecrc_pages_oahu.py

Batch-processes every ECRC filing PDF sitting in raw_filings\\, finds each of
the 5 target pages (heat rate, page3 generation, page4 purchased,
page6 FOAC biodiesel, page14 res bill) by matching distinctive header text
on each page, and saves each match as its own single-page PDF.

Every target page is located by SEARCHING page text for a unique header
phrase -- never by a fixed page number -- because the actual position of
each attachment shifts from filing to filing (e.g. heat rate has appeared
on page 12 in some filings, a different page in others).

Once ALL 5 pages have been successfully found and saved for a filing, the
original filing PDF is moved from raw_filings\\ to processed_filings\\.
If any page is missing, the filing is left in raw_filings\\ so it's
obviously still incomplete, and whichever pages WERE found are not
re-extracted on the next run (idempotent / safe to re-run).

Requires: pip install PyPDF2 pdfplumber
"""

import re
import shutil
from pathlib import Path

import pdfplumber
from PyPDF2 import PdfReader, PdfWriter


# ── Base path -------------------------------------------------------------
# The data folders live one level up from this script (in scripts\), in the
# ecrc\ parent folder, so this works unchanged no matter where the whole
# project folder is copied to.
BASE_DIR = Path(__file__).resolve().parent.parent

RAW_FILINGS_DIR = BASE_DIR / "raw_filings"
PROCESSED_FILINGS_DIR = BASE_DIR / "processed_filings"


# ── Helpers -----------------------------------------------------------------

def normalize(text: str) -> str:
    """Collapse all whitespace (spaces, newlines, tabs) into single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def page_matches(page_text: str, required_phrases: list[str]) -> bool:
    """
    Return True if every phrase in required_phrases appears somewhere in
    the page text. Matching is case-insensitive and whitespace-normalized,
    which catches PDF extraction quirks (extra spaces, mid-phrase line
    breaks) without needing a separate fallback strategy.
    """
    haystack = normalize(page_text).upper()
    return all(normalize(phrase).upper() in haystack for phrase in required_phrases)


# ── Page type definitions -----------------------------------------------
#
# Each entry defines one of the 5 pages you're extracting. To add a new
# page type in the future, add one more dict here -- no other code needs
# to change.
#
#   name             : short identifier, used in output filenames and folder names
#   output_subfolder : page-type folder name under BASE_DIR (matches your
#                       existing oahu\ecrc\<folder> convention)
#   match_phrases     : list of phrases that must ALL appear on the page
#                       (verified unique against a real filing -- see notes)
#   filename_suffix   : appended to the source filing's filename for the output

PAGE_DEFINITIONS = [
    {
        "name": "heat_rate",
        "output_subfolder": "heat_rate",
        "match_phrases": ["RECORDED HEAT RATE DATA"],
        "filename_suffix": "heat_rate",
    },
    {
        "name": "generation_component",
        "output_subfolder": "generation_component",
        "match_phrases": ["GENERATION COMPONENT"],
        "filename_suffix": "generation_component",
    },
    {
        "name": "purchased_component",
        "output_subfolder": "purchased_component",
        "match_phrases": ["PURCHASED ENERGY COMPONENT"],
        "filename_suffix": "purchased_component",
    },
    {
        "name": "foac_biodiesel",
        "output_subfolder": "foac_biodiesel",
        "match_phrases": ["FOAC", "ATTACHMENT 3"],
        "filename_suffix": "foac_biodiesel",
    },
    {
        "name": "res_bill",
        "output_subfolder": "res_bill",
        "match_phrases": ["CALCULATIONS OF THE AVERAGE RESIDENTIAL CUSTOMER BILL"],
        "filename_suffix": "res_bill",
    },
]


# ── Core extraction logic ----------------------------------------------------

def find_matching_page_index(pdf_path: Path, match_phrases: list[str]) -> int | None:
    """
    Scan every page of the PDF and return the 0-based index of the first
    page whose text contains all of match_phrases. Returns None if no
    page matches.
    """
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if page_matches(text, match_phrases):
                return i
    return None


def extract_single_page(pdf_path: Path, page_index: int, output_path: Path) -> None:
    """Save a single page (by 0-based index) from pdf_path as its own PDF."""
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    writer.add_page(reader.pages[page_index])
    with open(output_path, "wb") as f:
        writer.write(f)


def process_filing(pdf_path: Path) -> bool:
    """
    Run all 5 page extractions for a single filing PDF.
    Returns True only if every page type was found and saved successfully.
    Already-extracted pages (from a prior partial run) are skipped, so this
    is safe to re-run on a filing that failed partway through.
    """
    print(f"\n[FILING] {pdf_path.name}")
    all_succeeded = True

    for page_def in PAGE_DEFINITIONS:
        output_folder = BASE_DIR / page_def["output_subfolder"]
        output_folder.mkdir(parents=True, exist_ok=True)

        output_filename = f"{pdf_path.stem}_{page_def['filename_suffix']}.pdf"
        output_path = output_folder / output_filename
        processed_marker = output_folder / "processed_page" / output_filename

        # Skip re-extraction if this page was already produced by a prior run
        # (either still sitting as the raw extract, or already moved to processed_page)
        if output_path.exists() or processed_marker.exists():
            print(f"  SKIP   {page_def['name']:22s} -> already extracted")
            continue

        try:
            page_index = find_matching_page_index(pdf_path, page_def["match_phrases"])

            if page_index is None:
                print(f"  MISSING {page_def['name']:22s} -> no matching page found")
                all_succeeded = False
                continue

            extract_single_page(pdf_path, page_index, output_path)
            print(f"  OK     {page_def['name']:22s} -> {output_filename}  (page {page_index + 1})")

        except Exception as exc:
            print(f"  ERROR  {page_def['name']:22s} -> {exc}")
            all_succeeded = False

    return all_succeeded


def main():
    RAW_FILINGS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_FILINGS_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(RAW_FILINGS_DIR.glob("*.pdf"))

    if not pdf_files:
        print(f"No filing PDFs found in: {RAW_FILINGS_DIR}")
        return

    print(f"Found {len(pdf_files)} filing(s) in raw_filings.\n")
    print("=" * 60)

    fully_processed = 0
    incomplete = 0

    for pdf_path in pdf_files:
        success = process_filing(pdf_path)

        if success:
            destination = PROCESSED_FILINGS_DIR / pdf_path.name
            shutil.move(str(pdf_path), str(destination))
            print(f"  -> All 5 pages found. Filing moved to processed_filings.")
            fully_processed += 1
        else:
            print(f"  -> Incomplete. Filing left in raw_filings for review.")
            incomplete += 1

    print("\n" + "=" * 60)
    print(f"Done. {fully_processed} filing(s) fully processed, {incomplete} incomplete.")
    if incomplete:
        print("Check the MISSING/ERROR lines above for filings still in raw_filings.")


if __name__ == "__main__":
    main()
