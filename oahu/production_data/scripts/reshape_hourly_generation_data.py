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

    all_sheets = []

    # Use a context manager so the file handle is released promptly — the file
    # still needs to be renamed later, by upload_oahu_production.py, and
    # Windows keeps an open file locked.
    with pd.ExcelFile(file_path) as xl:
        sheet_names = xl.sheet_names
        print(f"  - Found {len(sheet_names)} worksheet(s): {sheet_names}")

        for sheet in sheet_names:
            print(f"  - Reading sheet: '{sheet}'")
            df = pd.read_excel(xl, sheet_name=sheet)

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


def process_new_files(raw_directory, output_file):
    """
    Process only the Excel files sitting in raw_directory (files already
    archived to processed_data are never re-read), reshape each to long
    format, and merge the result into any existing output_file so the
    combined CSV keeps its full history.

    Parameters:
    raw_directory: directory containing newly-dropped Excel files
    output_file:   Path to the combined CSV (read for prior history, then overwritten)

    Returns:
    (combined_df, successfully_processed_paths) or (None, []) if there was
    nothing new to process
    """
    raw_path = Path(raw_directory)
    excel_files = sorted(
        list(raw_path.glob('*.xlsx')) + list(raw_path.glob('*.xls'))
    ) if raw_path.exists() else []

    if not excel_files:
        print(f"No new Excel files found in '{raw_directory}' — nothing to do.")
        return None, []

    print(f"\nFound {len(excel_files)} new Excel file(s) to process\n")

    all_data = []
    processed_paths = []

    for excel_file in excel_files:
        try:
            df_reshaped = process_excel_file(excel_file)
            if df_reshaped is not None:
                all_data.append(df_reshaped)
                processed_paths.append(excel_file)
        except Exception as e:
            print(f"  ERROR processing {excel_file.name}: {str(e)}")
            continue

    if not all_data:
        print("\nERROR: No data was successfully processed!")
        return None, []

    new_data_df = pd.concat(all_data, ignore_index=True)

    # Merge with existing combined CSV, if any, so prior history is preserved
    # without ever re-reading the Excel files already archived in processed_data.
    output_path = Path(output_file)
    if output_path.exists():
        print(f"Merging with existing combined data: {output_path}")
        existing_df = pd.read_csv(output_path, parse_dates=['datetime'])
        combined_df = pd.concat([existing_df, new_data_df], ignore_index=True)
    else:
        combined_df = new_data_df

    # Sort and deduplicate (in case the same datetime/plant appears twice)
    combined_df = (
        combined_df
        .drop_duplicates(subset=['datetime', 'plant_name'])
        .sort_values(['datetime', 'plant_name'])
        .reset_index(drop=True)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined_df.to_csv(output_path, index=False)

    print(f"\nSuccess! Combined data saved to: {output_path}")
    print(f"Total rows:             {len(combined_df):,}")
    print(f"Date range:             {combined_df['datetime'].min()} to {combined_df['datetime'].max()}")
    print(f"Unique plants:          {combined_df['plant_name'].nunique()}")

    return combined_df, processed_paths


# ── Main execution ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    BASE_DIR      = Path(__file__).resolve().parent.parent
    RAW_DIR       = BASE_DIR / "raw_data"
    OUTPUT_FILE   = BASE_DIR / "csv_output" / "combined_oahu_production_data.csv"

    print("=" * 70)
    print("Oahu Production Data Processing Script")
    print("=" * 70)

    result, processed_paths = process_new_files(RAW_DIR, OUTPUT_FILE)

    if result is not None:
        print("\nFirst 10 rows of combined data:")
        print(result.head(10))
        print("\nLast 10 rows of combined data:")
        print(result.tail(10))

        print(
            "\nRaw files remain in raw_data\\ until upload_oahu_production.py "
            "confirms they're loaded into the database."
        )
