import os
import pandas as pd
from datetime import datetime
from pathlib import Path

# Folder with your CSV files
BASE_DIR    = Path(__file__).resolve().parent.parent / "purchased_component"
csv_folder  = BASE_DIR / "csv_output"
output_file = BASE_DIR / "csv_output" / "combined_purchased_data.csv"

print("=" * 80)
print("COMBINING CSV FILES")
print("=" * 80)

# Get all CSV files in the folder
csv_files = sorted([f for f in os.listdir(csv_folder) if f.lower().endswith('.csv') and f != "combined_purchased_data.csv"])

if not csv_files:
    print("\n❌ No CSV files found in the folder!")
    exit()

print(f"\n📁 Found {len(csv_files)} CSV files to combine\n")

# Read the first file to get the structure (Line and PURCHASED ENERGY COMPONENT columns)
first_file = csv_folder / csv_files[0]
df_combined = pd.read_csv(first_file, encoding='cp1252')

print(f"✓ Loaded base structure from: {csv_files[0]}")
print(f"  Columns: {list(df_combined.columns)}")

# Now read and merge the remaining files
for csv_file in csv_files[1:]:
    file_path = csv_folder / csv_file
    
    try:
        df_temp = pd.read_csv(file_path, encoding='cp1252')
        
        # Get the date column (should be the 3rd column, not "Line" or "PURCHASED ENERGY COMPONENT")
        date_cols = [col for col in df_temp.columns if col not in ['Line', 'PURCHASED ENERGY COMPONENT']]
        
        if date_cols:
            date_col = date_cols[0]
            # Merge this date column into the combined dataframe
            df_combined[date_col] = df_temp[date_col]
            print(f"✓ Added data from: {csv_file} (column: {date_col})")
        else:
            print(f"⚠ Skipped {csv_file}: No date column found")
            
    except Exception as e:
        print(f"❌ Error reading {csv_file}: {e}")

# Sort date columns chronologically (skip Line and PURCHASED ENERGY COMPONENT)
structure_cols = ['Line', 'PURCHASED ENERGY COMPONENT']
date_cols = [col for col in df_combined.columns if col not in structure_cols]

# Try to sort date columns
try:
    date_cols_sorted = sorted(date_cols, key=lambda x: datetime.strptime(x, '%Y-%m-%d'))
    final_cols = structure_cols + date_cols_sorted
    df_combined = df_combined[final_cols]
    print(f"\n✓ Sorted {len(date_cols_sorted)} date columns chronologically")
except:
    print(f"\n⚠ Could not sort date columns chronologically, keeping original order")

# Save combined file
df_combined.to_csv(output_file, index=False, encoding='cp1252')

print(f"\n" + "=" * 80)
print(f"✅ COMBINED FILE SAVED!")
print(f"=" * 80)
print(f"📄 Output file: {output_file}")
print(f"📊 Dimensions: {df_combined.shape[0]} rows × {df_combined.shape[1]} columns")
print(f"📅 Date columns: {len(date_cols)}")
print("\nFirst few rows:")
print(df_combined.head(10).to_string())
