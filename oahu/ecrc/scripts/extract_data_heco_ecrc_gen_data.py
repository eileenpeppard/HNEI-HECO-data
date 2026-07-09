#!/usr/bin/env python3
"""
Extract Hawaiian Electric Company Energy Cost Recovery (ECR) filing data from PDFs
and save to CSV format.
"""

import os
import re
from pathlib import Path
from datetime import datetime
import pdfplumber
import pandas as pd

# Filepath to process
INPUT_DIR = Path(__file__).resolve().parent.parent / "generation_component"
OUTPUT_CSV = INPUT_DIR / "csv_output" / "generation_component_extracted.csv"


def parse_date_from_filename(filename):
    """
    Extract date from filename like 'ecrc_oahu_2025_08_generation_component.pdf'
    Returns date in MM/DD/YY format
    """
    pattern = r'(\d{4})_(\d{2})_generation_component\.pdf'
    match = re.search(pattern, filename)
    if match:
        year = match.group(1)
        month = match.group(2)
        # Format as M/D/YY
        date_str = f"{int(month)}/1/{year[-2:]}"
        return date_str
    return None


def extract_ecr_data(pdf_path):
    """
    Extract ECR data from a single PDF file.
    
    Returns a list of dictionaries with date, component, and value.
    """
    data_rows = []
    filename = os.path.basename(pdf_path)
    date_str = parse_date_from_filename(filename)
    
    if not date_str:
        print(f"Warning: Could not parse date from filename: {filename}")
        return data_rows
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Get the first page
            page = pdf.pages[0]
            text = page.extract_text()
            
            if not text:
                print(f"Warning: No text extracted from {filename}")
                return data_rows
            
            # Normalize whitespace for easier matching
            text_normalized = ' '.join(text.split())
            
            # Extract major energy values
            # Line 17: COMPOSITE COST OF GENERATION, MAJOR ENERGY ¢/mmbtu
            # This spans two lines, so use a more flexible pattern
            match = re.search(r'17\s*COMPOSITE COST OF GENERATION,.*?MAJOR ENERGY ¢/mmbtu\s+([\d,]+\.?\d*)', text_normalized)
            if match:
                value = match.group(1).replace(',', '')
                data_rows.append({
                    'Date': date_str,
                    'component': 'major energy composite cost of generation cents/mmbtu',
                    'value': float(value)
                })
            
            # Line 18: % Input to system kWh Mix
            match = re.search(r'18\s*%\s+Input to system kWh Mix\s+([\d,]+\.?\d*)', text_normalized)
            if match:
                value = match.group(1).replace(',', '')
                data_rows.append({
                    'Date': date_str,
                    'component': 'major energy % input into system mix',
                    'value': float(value)
                })
            
            # Line 23: Weighted Efficiency Factor, mmbtu/kWh
            match = re.search(r'23\s*Weighted Efficiency Factor,\s*mmbtu/kWh\s+\[.*?\]\s+([\d,]+\.?\d+)', text_normalized)
            if match:
                value = match.group(1).replace(',', '')
                data_rows.append({
                    'Date': date_str,
                    'component': 'major energy weighted eff factor mmbtu/kwh',
                    'value': float(value)
                })
            
            # Line 24: WEIGHTED MAJOR ENERGY COST, ¢/kWh Sales
            match = re.search(r'24\s*WEIGHTED MAJOR ENERGY COST,?\s*¢/kWh Sales\s+\(lines.*?\)\s+([\d,]+\.?\d+)', text_normalized)
            if match:
                value = match.group(1).replace(',', '')
                data_rows.append({
                    'Date': date_str,
                    'component': 'major energy weighted energy cost cents/kwh',
                    'value': float(value)
                })
            
            # Line 31: MAJOR ENERGY GENERATION FACTOR, ¢/KWH
            # This also spans multiple lines
            match = re.search(r'31\s*MAJOR ENERGY GENERATION FACTOR,.*?¢/KWH\s+\(Line.*?\)\s+([\d,]+\.?\d+)', text_normalized)
            if match:
                value = match.group(1).replace(',', '')
                data_rows.append({
                    'Date': date_str,
                    'component': 'major energy generation factor cents/kwh',
                    'value': float(value)
                })
            
            # Line 32h: COMPOSITE COST OF MINOR ENERGY, ¢/kWh
            # Format is: "32hCOMPOSITE COST OF MINOR BTU MIX, % ENERGY, ¢/kWh 13.793"
            match = re.search(r'32h\s*COMPOSITE COST OF MINOR.*?ENERGY,\s*¢/kWh\s+([\d,]+\.?\d+)', text_normalized)
            if match:
                value = match.group(1).replace(',', '')
                data_rows.append({
                    'Date': date_str,
                    'component': 'minor energy composite cost cents/kwh',
                    'value': float(value)
                })
            
            # Line 33: % Input to System kWh Mix (for minor energy)
            match = re.search(r'33\s*%\s+Input to System kWh Mix\s+([\d,]+\.?\d+)', text_normalized)
            if match:
                value = match.group(1).replace(',', '')
                data_rows.append({
                    'Date': date_str,
                    'component': 'minor energy % input into system mix',
                    'value': float(value)
                })
            
            # Line 44: MINOR ENERGY FACTOR, ¢/kWh
            # Format is: "44MINOR ENERGY FACTOR, Fuel Type mmbtu/kwh Other Eff Factor ¢/kWh (Line 42 x 43) 0.23185"
            match = re.search(r'44\s*MINOR ENERGY FACTOR,.*?¢/kWh\s+\(Line.*?\)\s+([\d,]+\.?\d+)', text_normalized)
            if match:
                value = match.group(1).replace(',', '')
                data_rows.append({
                    'Date': date_str,
                    'component': 'minor energy factor cents/kwh',
                    'value': float(value)
                })
            
            # Line 47: TOTAL GENERATION FACTOR, ¢/KWH
            # Format is: "47TOTAL GENERATION FACTOR, ¢/KWH (lines 45 + 46) - 10.76658"
            match = re.search(r'47\s*TOTAL GENERATION FACTOR,.*?¢/KWH\s+\(lines.*?\)\s*-?\s*([\d,]+\.?\d+)', text_normalized)
            if match:
                value = match.group(1).replace(',', '')
                data_rows.append({
                    'Date': date_str,
                    'component': 'total generation factor cents/kwh',
                    'value': float(value)
                })
            
    except Exception as e:
        print(f"Error processing {filename}: {str(e)}")
    
    return data_rows


def process_all_pdfs():
    """
    Process all PDF files in INPUT_DIR and combine results.

    Returns a pandas DataFrame with all extracted data.
    """
    all_data = []

    if not INPUT_DIR.exists():
        print(f"Error: Directory does not exist: {INPUT_DIR}")
        return pd.DataFrame()

    # Find all PDF files
    pdf_files = sorted(INPUT_DIR.glob("*.pdf"))

    if not pdf_files:
        print(f"Warning: No PDF files found in {INPUT_DIR}")
        return pd.DataFrame()

    print(f"Found {len(pdf_files)} PDF file(s) to process")

    for pdf_file in pdf_files:
        print(f"Processing: {pdf_file.name}")
        data = extract_ecr_data(pdf_file)
        all_data.extend(data)

    # Create DataFrame
    df = pd.DataFrame(all_data)

    return df


def main():
    """Main execution function"""
    print("=" * 60)
    print("HECO Energy Cost Recovery Data Extraction Tool")
    print("=" * 60)
    print()
    
    # Process PDFs
    df = process_all_pdfs()

    if df.empty:
        print("No data extracted. Please check the PDF directory and files.")
        return

    # Sort by date and component
    df = df.sort_values(['Date', 'component'])

    # Display summary
    print(f"\nExtracted {len(df)} data points")
    print(f"Date range: {df['Date'].min()} to {df['Date'].max()}")
    print(f"\nFirst few rows:")
    print(df.head(10))

    # Save to CSV
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nData saved to: {OUTPUT_CSV}")
    
    # Also create a summary by date
    print("\n" + "=" * 60)
    print("Summary by Date:")
    print("=" * 60)
    for date in sorted(df['Date'].unique()):
        date_data = df[df['Date'] == date]
        print(f"\n{date}:")
        for _, row in date_data.iterrows():
            print(f"  {row['component']}: {row['value']}")


if __name__ == "__main__":
    main()