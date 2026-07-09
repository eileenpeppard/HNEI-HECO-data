import pandas as pd
import os
from pathlib import Path

def process_excel_file(file_path):
    """
    Process a single Excel file — all worksheets — and reshape each to long format.

    Parameters:
    file_path: Path to the Excel file

    Returns:
    DataFrame with columns: datetime, plant_name, mwh
    """
    print(f"Processing: {os.path.basename(file_path)}")

    xl = pd.ExcelFile(file_path)
    sheet_names = xl.sheet_names
    print(f"  - Found {len(sheet_names)} worksheet(s): {sheet_names}")

    all_sheets = []

    for sheet in sheet_names:
        print(f"  - Reading sheet: '{sheet}'")
        df = pd.read_excel(file_path, sheet_name=sheet)

        # Check that a DateTime column exists
        if 'DateTime' not in df.columns:
            print(f"    WARNING: No 'DateTime' column found in sheet '{sheet}' — skipping.")
            continue

        # Remove footer rows (rows where DateTime is NaN)
        df = df[df['DateTime'].notna()].copy()

        # Convert DateTime column, drop unconvertible rows
        df['DateTime'] = pd.to_datetime(df['DateTime'], errors='coerce')
        df = df[df['DateTime'].notna()].copy()

        if len(df) == 0:
            print(f"    WARNING: No valid data rows found in sheet '{sheet}' — skipping.")
            continue

        # Reshape from wide to long format
        df_long = df.melt(
            id_vars=['DateTime'],
            var_name='plant_name',
            value_name='mwh'
        )

        df_long = df_long.rename(columns={'DateTime': 'datetime'})
        df_long = df_long.sort_values(['datetime', 'plant_name']).reset_index(drop=True)

        print(f"    -> Reshaped to {len(df_long):,} rows ({len(df)} timestamps x {len(df.columns)-1} plants)")
        all_sheets.append(df_long)

    if not all_sheets:
        print(f"  ERROR: No valid data found in any sheet of this file.")
        return None

    return pd.concat(all_sheets, ignore_index=True)


def process_all_files(input_directory, output_file):
    """
    Process all Excel files in the directory, across all worksheets,
    and combine everything into one CSV.

    Parameters:
    input_directory: Path to directory containing Excel files
    output_file:     Path where the combined CSV should be saved
    """
    input_path = Path(input_directory)

    if not input_path.exists():
        print(f"ERROR: Directory '{input_directory}' does not exist!")
        return

    excel_files = sorted(
        list(input_path.glob('*.xlsx')) + list(input_path.glob('*.xls'))
    )

    if not excel_files:
        print(f"ERROR: No Excel files found in '{input_directory}'")
        return

    print(f"\nFound {len(excel_files)} Excel file(s) to process\n")

    all_data = []

    for excel_file in excel_files:
        try:
            df_reshaped = process_excel_file(excel_file)
            if df_reshaped is not None:
                all_data.append(df_reshaped)
        except Exception as e:
            print(f"  ERROR processing {excel_file.name}: {str(e)}")
            continue

    if not all_data:
        print("\nERROR: No data was successfully processed!")
        return

    print(f"\nCombining all data...")
    combined_df = pd.concat(all_data, ignore_index=True)

    # Sort and deduplicate (in case the same datetime/plant appears in multiple sheets)
    combined_df = (
        combined_df
        .drop_duplicates(subset=['datetime', 'plant_name'])
        .sort_values(['datetime', 'plant_name'])
        .reset_index(drop=True)
    )

    # Make sure the output folder exists
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    combined_df.to_csv(output_file, index=False)

    print(f"\nSuccess! Combined data saved to: {output_file}")
    print(f"Total rows:             {len(combined_df):,}")
    print(f"Date range:             {combined_df['datetime'].min()} to {combined_df['datetime'].max()}")
    print(f"Unique plants:          {combined_df['plant_name'].nunique()}")

    return combined_df


# ── Main execution ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    INPUT_DIR   = Path(__file__).resolve().parent / "raw_data"
    OUTPUT_FILE = Path(__file__).resolve().parent / "output" / "combined_oahu_production_data.csv"

    print("=" * 70)
    print("Oahu Production Data Processing Script")
    print("=" * 70)

    result = process_all_files(INPUT_DIR, OUTPUT_FILE)

    if result is not None:
        print("\nFirst 10 rows of combined data:")
        print(result.head(10))
        print("\nLast 10 rows of combined data:")
        print(result.tail(10))