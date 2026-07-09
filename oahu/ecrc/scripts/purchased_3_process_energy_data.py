import pandas as pd
import numpy as np
from pathlib import Path

# File paths
BASE_DIR     = Path(__file__).resolve().parent.parent / "purchased_component"
input_csv    = BASE_DIR / "csv_output" / "combined_purchased_data.csv"
output_csv   = BASE_DIR / "csv_output" / "purchased_energy.csv"
erc_list_csv = BASE_DIR / "erc_list.csv"

print("=" * 80)
print("PROCESSING PURCHASED ENERGY DATA")
print("=" * 80)

# Load the combined data
df = pd.read_csv(input_csv, encoding='cp1252')
print(f"\n✓ Loaded data: {df.shape[0]} rows × {df.shape[1]} columns")

# Get date columns (all columns except Line and PURCHASED ENERGY COMPONENT)
date_columns = [col for col in df.columns if col not in ['Line', 'PURCHASED ENERGY COMPONENT']]
print(f"✓ Found {len(date_columns)} date columns")

# ============================================================================
# STEP 1: PROCESS PRICE DATA (Lines 48-67.6)
# ============================================================================
print("\n" + "=" * 80)
print("STEP 1: PROCESSING PRICE DATA (Lines 48-67.6)")
print("=" * 80)

# Define price line range
price_lines = [
    '48', '49', '50', '51', '52', '53', '54', '55', '56', '57', '58', '59', 
    '60', '61', '62', '63', '64', '65', '66', '67', '67.1', '67.2', '67.3', 
    '67.4', '67.5', '67.6'
]

# Filter rows for price data
df_price = df[df['Line'].astype(str).isin(price_lines)].copy()
print(f"✓ Filtered {len(df_price)} price rows")

# Reshape: melt date columns into rows
df_price_long = df_price.melt(
    id_vars=['Line', 'PURCHASED ENERGY COMPONENT'],
    value_vars=date_columns,
    var_name='date',
    value_name='price_cents_per_kwh'
)

# Rename columns
df_price_long = df_price_long.rename(columns={'PURCHASED ENERGY COMPONENT': 'erc_name'})

# Remove Line column and rows with missing data
df_price_long = df_price_long[['date', 'erc_name', 'price_cents_per_kwh']]
df_price_long = df_price_long.dropna(subset=['price_cents_per_kwh'])

# Remove rows where price_cents_per_kwh is empty string, 'NULL', or 'nan'
df_price_long = df_price_long[
    (df_price_long['price_cents_per_kwh'].astype(str).str.strip() != '') &
    (df_price_long['price_cents_per_kwh'].astype(str).str.upper() != 'NULL') &
    (df_price_long['price_cents_per_kwh'].astype(str).str.upper() != 'NAN')
]

print(f"✓ Reshaped to long format: {len(df_price_long)} records")
print(f"  Sample:")
print(df_price_long.head(10).to_string(index=False))

# ============================================================================
# STEP 2: PROCESS PERCENTAGE DATA (Lines 68-87.6)
# ============================================================================
print("\n" + "=" * 80)
print("STEP 2: PROCESSING PERCENTAGE DATA (Lines 68-87.6)")
print("=" * 80)

# Define percentage line range
pct_lines = [
    '68', '69', '70', '71', '72', '73', '73a', '74', '75', '76', '77', '78', 
    '79', '80', '81', '82', '83', '84', '85', '86', '87', '87.1', '87.2', 
    '87.3', '87.4', '87.5', '87.6', '87a', '87b'
]

# Filter rows for percentage data
df_pct = df[df['Line'].astype(str).isin(pct_lines)].copy()
print(f"✓ Filtered {len(df_pct)} percentage rows")

# Reshape: melt date columns into rows
df_pct_long = df_pct.melt(
    id_vars=['Line', 'PURCHASED ENERGY COMPONENT'],
    value_vars=date_columns,
    var_name='date',
    value_name='%_of_purchased'
)

# Rename columns
df_pct_long = df_pct_long.rename(columns={'PURCHASED ENERGY COMPONENT': 'erc_name'})

# Remove Line column and rows with missing data
df_pct_long = df_pct_long[['date', 'erc_name', '%_of_purchased']]
df_pct_long = df_pct_long.dropna(subset=['%_of_purchased'])

# Remove rows where %_of_purchased is empty string, 'NULL', or 'nan'
df_pct_long = df_pct_long[
    (df_pct_long['%_of_purchased'].astype(str).str.strip() != '') &
    (df_pct_long['%_of_purchased'].astype(str).str.upper() != 'NULL') &
    (df_pct_long['%_of_purchased'].astype(str).str.upper() != 'NAN')
]

print(f"✓ Reshaped to long format: {len(df_pct_long)} records")
print(f"  Sample:")
print(df_pct_long.head(10).to_string(index=False))

# ============================================================================
# STEP 3: JOIN THE TWO TABLES
# ============================================================================
print("\n" + "=" * 80)
print("STEP 3: JOINING PRICE AND PERCENTAGE DATA")
print("=" * 80)

# Join on erc_name and date
df_final = pd.merge(
    df_price_long,
    df_pct_long,
    on=['erc_name', 'date'],
    how='inner'
)

# Reorder columns as specified
df_final = df_final[['erc_name', 'date', 'price_cents_per_kwh', '%_of_purchased']]

# Sort by date and erc_name
df_final = df_final.sort_values(['date', 'erc_name']).reset_index(drop=True)

print(f"✓ Joined data: {len(df_final)} records")
print(f"\n  Final data preview:")
print(df_final.head(20).to_string(index=False))

# ============================================================================
# SAVE OUTPUT
# ============================================================================
print("\n" + "=" * 80)
print("SAVING OUTPUT")
print("=" * 80)

df_final.to_csv(output_csv, index=False, encoding='cp1252')

print(f"✅ Output saved to: {output_csv}")
print(f"📊 Final dimensions: {df_final.shape[0]} rows × {df_final.shape[1]} columns")
print(f"📅 Date range: {df_final['date'].min()} to {df_final['date'].max()}")
print(f"🏢 Unique ERC names: {df_final['erc_name'].nunique()}")

# ============================================================================
# CLEAN UP: REMOVE UNUSED ROWS WITH ZERO VALUES
# ============================================================================
print("\n" + "=" * 80)
print("CLEANING UP: REMOVING 'UNUSED' WITH ZERO VALUES")
print("=" * 80)

# Convert to numeric for comparison
df_final['price_cents_per_kwh'] = pd.to_numeric(df_final['price_cents_per_kwh'], errors='coerce')
df_final['%_of_purchased'] = pd.to_numeric(df_final['%_of_purchased'], errors='coerce')

# Count rows before cleanup
rows_before = len(df_final)

# Remove rows where erc_name is 'Unused' and both values are 0
df_final = df_final[~(
    (df_final['erc_name'].str.strip().str.upper() == 'UNUSED') &
    (df_final['price_cents_per_kwh'] == 0) &
    (df_final['%_of_purchased'] == 0)
)]

rows_after = len(df_final)
print(f"✓ Removed {rows_before - rows_after} 'Unused' rows with zero values")
print(f"✓ Remaining rows: {rows_after}")

# Save cleaned data
df_final.to_csv(output_csv, index=False, encoding='cp1252')
print(f"✅ Updated output saved to: {output_csv}")

# ============================================================================
# COMPARE WITH ERC LIST
# ============================================================================
print("\n" + "=" * 80)
print("COMPARING ERC NAMES WITH REFERENCE LIST")
print("=" * 80)

try:
    df_erc_list = pd.read_csv(erc_list_csv, encoding='cp1252')
    print(f"✓ Loaded ERC list: {len(df_erc_list)} reference names")
    
    # Get unique ERC names from both files
    names_in_data = set(df_final['erc_name'].str.strip().unique())
    names_in_list = set(df_erc_list['erc_name'].str.strip().unique())
    
    # Find names in data but NOT in reference list
    names_not_in_list = names_in_data - names_in_list
    
    # Find names in reference list but NOT in data
    names_not_in_data = names_in_list - names_in_data
    
    print(f"\n📊 Comparison Results:")
    print(f"  - Names in processed data: {len(names_in_data)}")
    print(f"  - Names in reference list: {len(names_in_list)}")
    
    if names_not_in_list:
        print(f"\n⚠️ WARNING: {len(names_not_in_list)} names in DATA but NOT in reference list:")
        for name in sorted(names_not_in_list):
            print(f"     - '{name}'")
    else:
        print(f"\n✅ All names in data are in the reference list")
    
    if names_not_in_data:
        print(f"\n🔍 INFO: {len(names_not_in_data)} names in REFERENCE LIST but not in data:")
        for name in sorted(names_not_in_data):
            print(f"     - '{name}'")
    else:
        print(f"\n✅ All reference names appear in the data")
    
    # Perfect match?
    if names_in_data == names_in_list:
        print(f"\n✅ PERFECT MATCH: All names match exactly!")
    
except FileNotFoundError:
    print(f"❌ ERC list file not found: {erc_list_path}")
except Exception as e:
    print(f"❌ Error reading ERC list: {e}")

print("\n" + "=" * 80)
print("✨ PROCESSING COMPLETE!")
print("=" * 80)
