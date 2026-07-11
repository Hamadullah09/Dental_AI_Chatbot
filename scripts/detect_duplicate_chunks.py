from __future__ import annotations

import argparse

from cleanup_audit_lib import add_common_args, duplicate_chunk_rows, load_documents, report_dir, write_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect duplicate chunks across the Dental AI corpus.")
    add_common_args(parser)
    args = parser.parse_args()

    reports = report_dir(args.report_dir)
    docs = load_documents(args.db)
    rows, duplicate_ids = duplicate_chunk_rows(docs)
    write_csv(reports / "duplicate_chunks.csv", rows)
    groups = len({row["duplicate_chunk_group_id"] for row in rows})
    print(f"duplicate_chunks.csv written to: {reports}")
    print(f"duplicate chunk groups: {groups}")
    print(f"duplicate chunks marked for removal: {len(duplicate_ids)}")


if __name__ == "__main__":
    main()
