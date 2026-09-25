# heco_installed_solar

Quarterly cumulative installed PV (rooftop and utility-scale solar) for the three Hawaiian Electric
utilities, from 2012 Q3 onward.

## Source

The PDFs are the quarterly installed-solar summaries published by Hawaiian Electric at
<https://www.hawaiianelectric.com/clean-energy-hawaii/our-clean-energy-portfolio/quarterly-installed-solar-data>.
Each one-page report gives, per utility, the number of PV systems and installed capacity (MW),
with the residential vs. commercial & utility-scale split.

Hawaiian Electric marks the data "subject to change" and does revise earlier figures, so each
quarter's values are as reported at that time.

## Layout

```
heco_installed_solar\
  input\                     <- download new PDFs from the website and put them here
  archive\                   <- 03_upload_data.py moves PDFs here after a successful upload
  output\
    heco_installed_pv.csv    <- one row per utility per quarter, built by 02_extract_pv_data.py
  scripts\
    01_rename_pdfs.py        pv_summary_2Q_2026.pdf -> 2026_2Q_pv_summary.pdf (year first)
    02_extract_pv_data.py    reads the PDFs in input\ -> output\heco_installed_pv.csv
    03_upload_data.py        loads the CSV into Postgres, then archives the PDFs
  sql\
    create_installed_pv.sql  one-time setup: creates the database table
```

## Database

Data is uploaded to the **`hnei_heco`** database, **`statewide`** schema, **`installed_pv`** table
(`statewide.installed_pv`). The table was created once with:

```
psql hnei_heco -f sql/create_installed_pv.sql
```

| Column | Meaning |
|---|---|
| `date` | quarter-end "as of" date, e.g. `2026-06-30` |
| `utility` | `heco` = Hawaiian Electric (Oahu), `helco` = Hawai'i Electric Light, `meco` = Maui Electric |
| `num_systems` | number of installed PV systems |
| `pct_systems_residential`, `pct_systems_commercial` | share of systems, whole-number percent |
| `capacity_mw` | installed PV capacity, MW |
| `pct_capacity_residential`, `pct_capacity_commercial` | share of capacity, whole-number percent |

The percentage columns are empty for 2012 Q3, which did not report them. The report's Total row is
not stored; sum the three utilities instead.

## Adding a new quarter

1. Download the new PDF from the website above and put it in `input\`.
2. Run the scripts in order from this folder:
   ```
   python scripts/01_rename_pdfs.py
   python scripts/02_extract_pv_data.py
   python scripts/03_upload_data.py
   ```

`02_extract_pv_data.py` checks each report's three utility rows against its printed Total and
leaves out any PDF it can't read cleanly (it prints `FAIL` with the reason). `03_upload_data.py`
runs in a single transaction: if anything fails, including a quarter that is already in the
table, nothing is loaded and no PDFs are moved. Requires `pip install pdfplumber` and `psql`,
with connection details from the `PG*` environment variables or `~/.pgpass`.
