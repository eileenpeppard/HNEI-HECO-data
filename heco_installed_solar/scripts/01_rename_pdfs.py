"""
01_rename_pdfs.py

Renames the HECO installed-solar PDFs in input\\ so the year and quarter come
first, which makes the files sort chronologically in a folder listing:

    pv_summary_1Q_2013.pdf  ->  2013_1Q_pv_summary.pdf

Files that don't match the pv_summary_<N>Q_<YYYY>.pdf pattern (including
ones already renamed) are left alone, so the script is safe to re-run.

Run with --dry-run to preview the renames without changing anything.
"""

import argparse
import re
from pathlib import Path


# ── Base path -------------------------------------------------------------
# The input folder lives one level up from this script (in scripts\), in the
# heco_installed_solar\ parent folder.
BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_DIR = BASE_DIR / "input"

# pv_summary_1Q_2013.pdf -> prefix="pv_summary", quarter="1Q", year="2013"
OLD_NAME_PATTERN = re.compile(
    r"^(?P<prefix>.+)_(?P<quarter>[1-4]Q)_(?P<year>\d{4})\.pdf$", re.IGNORECASE
)


def new_name_for(filename: str) -> str | None:
    """Return the year-first name for filename, or None if it doesn't match."""
    match = OLD_NAME_PATTERN.match(filename)
    if not match:
        return None
    return f"{match['year']}_{match['quarter'].upper()}_{match['prefix']}.pdf"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[3])
    parser.add_argument(
        "--dry-run", action="store_true", help="show renames without doing them"
    )
    args = parser.parse_args()

    renamed = skipped = 0
    for pdf in sorted(INPUT_DIR.glob("*.pdf")):
        new_name = new_name_for(pdf.name)
        if new_name is None:
            skipped += 1
            continue

        target = pdf.with_name(new_name)
        if target.exists():
            print(f"SKIP  {pdf.name}: {new_name} already exists")
            skipped += 1
            continue

        print(f"{'WOULD RENAME' if args.dry_run else 'RENAME'}  {pdf.name} -> {new_name}")
        if not args.dry_run:
            pdf.rename(target)
        renamed += 1

    verb = "would be renamed" if args.dry_run else "renamed"
    print(f"\n{renamed} file(s) {verb}, {skipped} skipped.")


if __name__ == "__main__":
    main()
