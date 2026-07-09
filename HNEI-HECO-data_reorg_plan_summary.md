# HNEI-HECO-data Reorg — Status / Handoff Notes

**Date:** 2026-07-08
**Status: DONE** (except two manual follow-ups noted at the bottom — read those before assuming
everything is finished).

## Goal

Consolidate scattered code and data into one portable repo, `HNEI-HECO-data`, so the whole
folder can be copied to a server with no manual path edits. Currently focused on Oahu only;
structured so the same pattern can be replicated to Maui, Kauai, and Big Island later.

## Current state (as of this reorg, before the changes below were applied)

- **Code** lives in `Documents\GitHub\ECRC-and-Production\oahu\` — a git repo with 8 scripts
  that extract data from HECO ECRC PDF filings, plus a newly-added script
  (`260123 reshape hourly generation data v3 oahu.py`) that reshapes production-data Excel files.
- **Data** lives separately in `Documents\03_hnei_data_processing\oahu\ecrc\` (the folder open in
  VS Code) and `...\oahu\production_data\`.
- Every script has a hardcoded absolute path near the top (e.g.
  `Path(r"C:\Users\EileenPeppard\Documents\03_hnei_data_processing\oahu\ecrc\heat_rate")`), so it
  only works on this one machine.
- `Documents\03_hnei_data_processing\` also already contains `maui\`, `kauai\`, and `big_island\`
  folders with their own legacy scripts/data — these are **out of scope** for this round; only
  Oahu is being reorganized now.

## What was actually done

1. **Created** `Documents\03_hnei_data_processing\HNEI-HECO-data\` as the new repo root — this is
   what should eventually be copied to the server.
2. **Moved/copied the real data folders** into `HNEI-HECO-data\oahu\ecrc\` and
   `HNEI-HECO-data\oahu\production_data\`: `raw_filings`, `processed_filings`, `heat_rate`,
   `generation_component`, `purchased_component`, `foac_biodiesel`, `res_bill`, and
   `production_data\raw_data` / `processed_data` / `output`.
   - `production_data` moved cleanly (cut, not copied).
   - `ecrc` had to be **copied** instead of moved — it was open in VS Code at the time, and
     Windows wouldn't release the folder lock for a move/delete. See "Outstanding" below.
3. **Copied** the 8 ECRC scripts + the production-data script from the GitHub repo into those same
   folders, so code sits right next to the data it processes. The original GitHub repo
   (`Documents\GitHub\ECRC-and-Production`) was left untouched as a backup.
4. **Fixed each script's path** — replaced the one hardcoded line in all 9 scripts with
   `Path(__file__).resolve().parent / "<subfolder>"`, so each script finds its data by looking in
   its own folder instead of a fixed Windows path. Verified by resolving each path and counting
   files in it (see Verification below) — no script still references the old absolute path.
5. **Renamed** `260123 reshape hourly generation data v3 oahu.py` → `reshape_hourly_generation_data.py`,
   and pointed it at the `raw_data` / `output` subfolders (matching the naming convention already
   used elsewhere) instead of the production_data root.
6. **Small honesty cleanup**: `extract_data_res_bill_data.py`'s docstring said "HELCO (Big
   Island)" even though it actually processes Oahu data — corrected to say Oahu/HECO.
7. **Wrote a new `README.md`** at the `HNEI-HECO-data` root describing the pipeline as it actually
   exists today (replacing the old aspirational `oahu\ecrc\README.txt`, which described unbuilt
   Postgres/config.py/multi-island infrastructure — that file was deleted).
8. Removed the old `.claude\settings.local.json` that lived inside `ecrc\` (it only granted read
   access to the now-irrelevant GitHub repo path).
9. **`.gitignore`** created at the `HNEI-HECO-data` root, excluding PDFs/CSVs/Excel/`__pycache__`/`.claude`.

## Verification performed

- Grepped the whole `HNEI-HECO-data` folder for the old username/path — no matches in any script
  (only in this doc, which is expected since it's describing the reorg).
- Resolved each script's new path logic directly (via `py -c`) and confirmed it points at the
  right folder with the right file counts: `heat_rate\` → 7 PDFs, `raw_data\` → 1 Excel file, etc.
- Ran `extract_ecrc_data_heat_rate.py` directly — it started, resolved its path correctly, and
  stopped only because `pdfplumber` isn't installed in this Python environment. **Full end-to-end
  execution (actually parsing a PDF/Excel file) has not been verified** — only path resolution.
  Once dependencies (`pip install pdfplumber PyPDF2 pandas numpy`) are installed, re-run each
  script for real to confirm output CSVs look right.

## Explicitly not doing (this round)

- Not touching `maui\`, `kauai\`, or `big_island\` folders or their existing legacy code/data.
- Not adding auto-archiving to the production-data script (moving processed Excel files into
  `processed_data\`) — that's a behavior change beyond path portability, flagged as a possible
  follow-up.
- Not deleting the original `GitHub\ECRC-and-Production` repo — kept as a backup until the new
  structure is verified working.

## Outstanding — do these next

1. **Delete the leftover old `ecrc` folder** at
   `Documents\03_hnei_data_processing\oahu\ecrc`. It's a stale duplicate left behind because it
   was open in VS Code when the move happened, so it was copied instead of moved. Everything in
   it is already safely copied into `HNEI-HECO-data\oahu\ecrc`. Once this file is not open in VS
   Code from that old path anymore, delete `03_hnei_data_processing\oahu\ecrc` (the old one, NOT
   the one under `HNEI-HECO-data`). `03_hnei_data_processing\oahu\production_data` is already
   gone (moved cleanly) — only `ecrc` is left behind.
2. **Initialize git** in `HNEI-HECO-data` — the `git` CLI wasn't on PATH in the shell used for
   this reorg, so `git init` was never run. Open `HNEI-HECO-data` in VS Code and use the Source
   Control panel → "Initialize Repository," or run `git init` from a terminal that has git on
   PATH. The `.gitignore` is already in place.
3. **Install dependencies and do a real end-to-end run** of at least one script
   (`pip install pdfplumber PyPDF2 pandas numpy`) to confirm actual data extraction still works,
   not just path resolution.
4. Not part of this reorg, left for later: migrating the existing legacy Maui/Kauai/Big Island
   code+data (found at `03_hnei_data_processing\maui\`, `\kauai\`, `\big_island\`) into this same
   `HNEI-HECO-data\<island>\` pattern.
