# HNEI-HECO-data

Code and data for extracting Hawaiian Electric Company (HECO) rate-filing and production data.
Code lives in a `scripts\` folder next to the data it processes so this whole folder can be
copied anywhere (including a server) without editing any file paths — every script locates its
own data folder at runtime via `Path(__file__).resolve().parent.parent`.

**Status:** Oahu is the only island built out so far.

## Layout

```
HNEI-HECO-data\
  oahu\
    ecrc\                          <- HECO ECRC PDF filing pipeline
      scripts\
        extract_ecrc_pages_oahu.py       Stage 1: splits raw filings into single-page PDFs
        extract_ecrc_data_heat_rate.py   Stage 2: heat rate page -> CSV
        extract_data_heco_ecrc_gen_data.py  Stage 2: generation component page -> CSV
        extract_data_res_bill_data.py    Stage 2: residential bill page -> CSV
        extract_ecrc_foac_data.py        Stage 2: FOAC/biodiesel page -> CSV
        purchased_pipeline.py            Stage 2: purchased energy (extract + combine + process)
      raw_filings\                 <- drop new filing PDFs here before running Stage 1
      processed_filings\           <- Stage 1 moves fully-extracted filings here
      heat_rate\  generation_component\  purchased_component\  foac_biodiesel\  res_bill\
                                    <- single-page PDFs + csv_output\ for each page type
    production_data\               <- PUC hourly generation Excel filings
      reshape_hourly_generation_data.py  reshapes wide-format Excel -> long-format CSV
      raw_data\                    <- drop new Excel filings here
      processed_data\              <- already-processed Excel filings
      output\                      <- combined_oahu_production_data.csv
```

## Running the Oahu ECRC pipeline

Install dependencies:
```
pip install pdfplumber PyPDF2 pandas numpy
```

Step 1 — extract target pages from raw filings:
```
python oahu/ecrc/scripts/extract_ecrc_pages_oahu.py
```
Scans every PDF in `raw_filings\`, extracts 5 pages per filing into their page-type folders, and
moves completed filings to `processed_filings\`. Safe to re-run (idempotent).

Step 2 — extract data from the single-page PDFs, run each independently after Step 1:
```
python oahu/ecrc/scripts/extract_ecrc_data_heat_rate.py
python oahu/ecrc/scripts/extract_data_heco_ecrc_gen_data.py
python oahu/ecrc/scripts/extract_data_res_bill_data.py
python oahu/ecrc/scripts/extract_ecrc_foac_data.py
```

The purchased energy component runs as a single pipeline (extract each PDF, combine into a wide
table, reshape/clean into the final long-format CSV):
```
python oahu/ecrc/scripts/purchased_pipeline.py               # -> csv_output\purchased_energy.csv
```
Per-PDF and combined-table debug CSVs are written to `csv_output\_intermediate\` along the way;
pass `--no-intermediate` to skip them.

## Running the Oahu production_data pipeline

```
python oahu/production_data/reshape_hourly_generation_data.py
```
Reads every `.xlsx`/`.xls` file in `raw_data\`, reshapes each worksheet from wide to long format,
and writes the combined result to `output\combined_oahu_production_data.csv`.

## Architecture

**Two-stage ECRC pipeline**: raw multi-page PDFs -> single-page extracts -> CSV data. Target pages
are located by searching for distinctive header text (e.g. `"RECORDED HEAT RATE DATA"`), never by
fixed page number, because page positions shift across filings. `PAGE_DEFINITIONS` at the top of
`extract_ecrc_pages_oahu.py` lists the 5 page types with their match phrases.

**File naming convention** for extracted single-page PDFs: `ecrc_oahu_YYYY_MM_<page_type>.pdf`.
The Stage 2 extractors parse year/month from this filename pattern.

## Future islands

`03_hnei_data_processing\maui\`, `\kauai\`, and `\big_island\` already have some legacy
scripts/data of their own (outside this repo). When those pipelines get rebuilt, the plan is to
replicate this same `<island>\ecrc\` and `<island>\production_data\` pattern here, reusing the
page-splitting and extraction logic where the PDF layouts allow it.
