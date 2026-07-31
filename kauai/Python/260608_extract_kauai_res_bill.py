import os
import re
import csv
import pdfplumber
from datetime import datetime
from pathlib import Path

# Directory containing the PDFs
pdf_directory = r"C:\Users\EileenPeppard\Documents\03_hnei_data_processing\kauai\ERAC"
output_csv = r"C:\Users\EileenPeppard\Documents\03_hnei_data_processing\kauai\ERAC\kauai_residential_rates.csv"

print("=" * 80)
print("EXTRACTING KAUAI UTILITY RESIDENTIAL RATES FROM PDFs")
print("=" * 80)

# Check if directory exists
if not os.path.exists(pdf_directory):
    print(f"\n❌ Directory not found: {pdf_directory}")
    exit(1)

# Find all PDF files
pdf_files = sorted([f for f in os.listdir(pdf_directory) if f.lower().endswith('.pdf')])

if not pdf_files:
    print(f"\n❌ No PDF files found in: {pdf_directory}")
    exit(1)

print(f"\n✓ Found {len(pdf_files)} PDF file(s)\n")

# Store extracted data
extracted_data = []

# Process each PDF
for pdf_file in pdf_files:
    pdf_path = os.path.join(pdf_directory, pdf_file)
    print(f"Processing: {pdf_file}")
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            found_data = False
            
            # Search through each page
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                
                # Look for the header "AVERAGE 500 KWH RESIDENTIAL USER"
                if "AVERAGE 500 KWH RESIDENTIAL USER" in text.upper():
                    print(f"  ✓ Found target header on page {page_num}")
                    
                    # Extract effective date (format: M/D/YY or MM/DD/YY or MM/DD/YYYY)
                    # Look for "Effective Date" with 2 or 4 digit year
                    date_match = re.search(
                        r'[Ee]ffective\s+[Dd]ate[:\s]*(\d{1,2})/(\d{1,2})/(\d{2,4})',
                        text
                    )
                    
                    if date_match:
                        month = date_match.group(1)
                        day = date_match.group(2)
                        year = date_match.group(3)
                        
                        # If year is 2 digits, assume 20xx
                        if len(year) == 2:
                            year = "20" + year
                        
                        # Convert to YYYY-MM-DD format
                        try:
                            date_obj = datetime.strptime(f"{month}/{day}/{year}", "%m/%d/%Y")
                            formatted_date = date_obj.strftime("%Y-%m-%d")
                        except ValueError:
                            print(f"    ⚠️  Could not parse date: {month}/{day}/{year}")
                            formatted_date = None
                    else:
                        print(f"    ⚠️  Could not find effective date")
                        formatted_date = None
                    
                    # Extract the charge amount
                    # Look for text like "Average 500 kWh Residential User" followed by a dollar amount
                    charge_match = re.search(
                        r'[Aa]verage\s+500\s+[Kk]Wh\s+[Rr]esidential\s+[Uu]ser[:\s]*\$?([\d,]+\.\d{2})',
                        text
                    )
                    
                    if charge_match:
                        charge = charge_match.group(1).replace(',', '')  # Remove commas if present
                        print(f"    ✓ Charge: ${charge}")
                    else:
                        # Try alternative pattern - just look for dollar amounts near the keyword
                        lines = text.split('\n')
                        charge = None
                        
                        for i, line in enumerate(lines):
                            if '500 kWh' in line and 'Residential' in line and 'User' in line:
                                # Check this line and next few lines for dollar amount
                                for j in range(i, min(i + 3, len(lines))):
                                    dollar_match = re.search(r'\$?([\d,]+\.\d{2})', lines[j])
                                    if dollar_match:
                                        charge = dollar_match.group(1).replace(',', '')
                                        break
                                if charge:
                                    break
                        
                        if charge:
                            print(f"    ✓ Charge: ${charge}")
                        else:
                            print(f"    ⚠️  Could not find charge amount")
                    
                    # Store the data if both date and charge were found
                    if formatted_date and charge:
                        extracted_data.append({
                            'date': formatted_date,
                            'charge$_@500kwh': charge,
                            'pdf_file': pdf_file
                        })
                        found_data = True
                        break  # Found data for this PDF, move to next
            
            if not found_data:
                print(f"  ⚠️  Could not find required data in {pdf_file}")
    
    except Exception as e:
        print(f"  ❌ Error processing {pdf_file}: {str(e)}")

# Write results to CSV
print("\n" + "=" * 80)
if extracted_data:
    # Sort by date
    extracted_data.sort(key=lambda x: x['date'])
    
    # Write to CSV
    with open(output_csv, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['date', 'charge$_@500kwh'])
        writer.writeheader()
        
        for row in extracted_data:
            writer.writerow({
                'date': row['date'],
                'charge$_@500kwh': row['charge$_@500kwh']
            })
    
    print(f"\n✅ Successfully extracted data from {len(extracted_data)} PDF(s)")
    print(f"✓ Saved to: {output_csv}\n")
    print("Data extracted:")
    print("-" * 40)
    for item in extracted_data:
        print(f"  {item['date']}: ${item['charge$_@500kwh']}")
else:
    print(f"\n❌ No data was successfully extracted from any PDFs")

print("\n" + "=" * 80)