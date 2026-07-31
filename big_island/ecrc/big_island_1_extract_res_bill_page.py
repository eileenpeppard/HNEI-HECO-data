"""
Find and extract the page containing "CALCULATIONS OF THE AVERAGE RESIDENTIAL CUSTOMER BILL"
from all PDFs in a folder and save as separate files.
Requires: pip install PyPDF2
"""

import re
from pathlib import Path
from PyPDF2 import PdfReader, PdfWriter

SEARCH_TEXT = "CALCULATIONS OF THE AVERAGE RESIDENTIAL CUSTOMER BILL"


def normalize(text: str) -> str:
    """Collapse all whitespace (spaces, newlines, tabs) into single spaces."""
    return re.sub(r'\s+', ' ', text).strip()


def text_matches(page_text: str) -> bool:
    """Try multiple matching strategies to catch different PDF extraction quirks."""
    upper = page_text.upper()

    # Strategy 1: direct match (works for clean PDFs)
    if SEARCH_TEXT in upper:
        return True

    # Strategy 2: normalize whitespace (catches extra spaces / line breaks mid-phrase)
    if SEARCH_TEXT in normalize(upper):
        return True

    # Strategy 3: match all key words present on the page regardless of order/spacing
    keywords = ["CALCULATIONS", "AVERAGE", "RESIDENTIAL", "CUSTOMER", "BILL"]
    if all(kw in upper for kw in keywords):
        return True

    # Strategy 4: HELCO PDFs label this page "ATTACHMENT 9" and include
    # "RESIDENTIAL", "CUSTOMER", and "BILL" — but PyPDF2 may miss "CALCULATIONS"
    helco_keywords = ["ATTACHMENT 9", "RESIDENTIAL", "CUSTOMER", "BILL"]
    if all(kw in upper for kw in helco_keywords):
        return True

    return False


def find_and_extract_page(input_folder: str, output_folder: str) -> None:
    input_path = Path(input_folder)
    output_path = Path(output_folder)

    # Create output folder if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)

    pdf_files = list(input_path.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in: {input_folder}")
        return

    print(f"Found {len(pdf_files)} PDF file(s). Processing...\n")

    success_count = 0
    skip_count = 0
    error_count = 0

    for pdf_file in sorted(pdf_files):
        try:
            reader = PdfReader(str(pdf_file))
            matched_page = None

            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text_matches(text):
                    matched_page = i
                    break

            if matched_page is None:
                print(f"  SKIPPED: {pdf_file.name}  (target text not found)")
                skip_count += 1
                continue

            writer = PdfWriter()
            writer.add_page(reader.pages[matched_page])

            output_filename = f"{pdf_file.stem}_res_bill.pdf"
            output_file = output_path / output_filename

            with open(output_file, "wb") as f:
                writer.write(f)

            print(f"  OK:      {pdf_file.name}  ->  {output_filename}  (page {matched_page + 1})")
            success_count += 1

        except Exception as e:
            print(f"  ERROR:   {pdf_file.name}  ({e})")
            error_count += 1

    print(f"\nDone! {success_count} extracted, {skip_count} skipped, {error_count} error(s).")
    print(f"Output folder: {output_folder}")


if __name__ == "__main__":
    INPUT_FOLDER  = r"C:\Users\EileenPeppard\Documents\03_hnei_data_processing\big_island\ecrc"
    OUTPUT_FOLDER = r"C:\Users\EileenPeppard\Documents\03_hnei_data_processing\big_island\ecrc\page14_res_bill"

    find_and_extract_page(INPUT_FOLDER, OUTPUT_FOLDER)
