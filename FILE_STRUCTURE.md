# HNEI-HECO-data — File Structure

Snapshot taken 2026-07-08. Regenerate by re-running a recursive directory listing if this drifts
out of date — this is a point-in-time map, not something scripts depend on.

```
HNEI-HECO-data\
├── README.md                              <- how to run the pipeline
├── HNEI-HECO-data_reorg_plan_summary.md   <- history of the code+data consolidation
├── FILE_STRUCTURE.md                      <- this file
├── .gitignore                             <- excludes *.pdf, *.csv, *.xlsx/.xls, __pycache__, .claude
│
└── oahu\
    ├── ecrc\                               (362 files — 8 scripts + data)
    │   ├── extract_ecrc_pages_oahu.py           Stage 1: splits raw filings into 5 single-page PDFs
    │   ├── extract_ecrc_data_heat_rate.py        Stage 2: heat_rate -> CSV
    │   ├── extract_data_heco_ecrc_gen_data.py     Stage 2: generation_component -> CSV
    │   ├── extract_data_res_bill_data.py          Stage 2: res_bill -> CSV
    │   ├── extract_ecrc_foac_data.py              Stage 2: foac_biodiesel -> CSV
    │   ├── purchased_1_extract_data.py            Stage 2: purchased energy, step 1/3
    │   ├── purchased_2_combine_csv_files.py       Stage 2: purchased energy, step 2/3
    │   ├── purchased_3_process_energy_data.py     Stage 2: purchased energy, step 3/3
    │   │
    │   ├── raw_filings\                    (1 file)    full ECRC filings awaiting Stage 1
    │   │                                                latest: oahu_ecrc_2026_07.pdf
    │   ├── processed_filings\              (139 files) full filings, all 5 pages already extracted
    │   │                                                range: 2015-01 through 2026-06
    │   │
    │   ├── heat_rate\                      (10 files)  single-page heat rate PDFs
    │   │   ├── processed_page\             (3)           already extracted to CSV: 2026-04 to 2026-06
    │   │   ├── csv_output\                 (0)           transient — cleared after each run
    │   │   └── (7 loose PDFs, 2025-09 to 2026-03 — not yet run through Stage 2)
    │   │
    │   ├── generation_component\           (10 files)
    │   │   ├── processed_page\             (10)          already extracted: 2025-09 to 2026-06
    │   │   └── csv_output\                 (0)
    │   │
    │   ├── purchased_component\            (8 files)
    │   │   ├── processed_page\             (6)           already extracted: 2026-01 to 2026-06
    │   │   ├── csv_output\                 (0)
    │   │   ├── Template_purchased.csv                    required: line-number template
    │   │   └── erc_list.csv                               reference: valid ERC names
    │   │
    │   ├── foac_biodiesel\                 (131 files)
    │   │   ├── processed_page\             (124)         already extracted: 2015-02 to 2026-06
    │   │   └── (7 loose PDFs, 2025-09 to 2026-03 — not yet run through Stage 2)
    │   │
    │   └── res_bill\                       (55 files)
    │       ├── processed_page\             (55)          already extracted: 2015-01 to 2026-06
    │       └── csv_output\                 (0)
    │
    └── production_data\                    (13 files — 1 script + data)
        ├── reshape_hourly_generation_data.py     wide-format Excel -> long-format CSV
        ├── raw_data\                        (1 file)    Excel filings awaiting processing
        │                                                latest: 2026-07-07
        ├── processed_data\                  (11 files)  already-processed Excel filings
        │                                                range: 2025-08 to 2026-06
        └── output\                          (0 files)   combined_oahu_production_data.csv lands here
```

## Notes worth knowing

- **`heat_rate\` and `foac_biodiesel\` each have PDFs sitting loose at the top level** (not yet in
  `processed_page\`) for the 2025-09 through 2026-03 range — meaning Stage 2 hasn't been run for
  those months yet, or those runs didn't archive them. Worth running the corresponding Stage 2
  script and checking whether the archiving step needs a manual push.
- **`csv_output\` folders are all empty** — that's expected; they're transient and get
  cleared/overwritten each run per the pipeline design in `README.md`.
- **`output\` under `production_data\` is empty** — `reshape_hourly_generation_data.py` hasn't
  been run yet since the move (see the "Outstanding" list in
  `HNEI-HECO-data_reorg_plan_summary.md`).
