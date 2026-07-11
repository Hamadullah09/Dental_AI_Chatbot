from __future__ import annotations

import argparse

from cleanup_audit_lib import add_common_args, chunk_cleaning_rows, load_documents, report_dir, write_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run clean and quality-score existing Dental AI chunks.")
    add_common_args(parser)
    args = parser.parse_args()

    reports = report_dir(args.report_dir)
    docs = load_documents(args.db)
    rows, noisy_removed = chunk_cleaning_rows(docs)
    write_csv(reports / "chunk_cleaning_dry_run.csv", rows)
    print(f"chunk_cleaning_dry_run.csv written to: {reports}")
    print(f"total chunks inspected: {len(rows)}")
    print(f"noisy chunks marked for removal: {noisy_removed}")


if __name__ == "__main__":
    main()
