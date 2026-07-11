from __future__ import annotations

import argparse

from cleanup_audit_lib import add_common_args, duplicate_document_groups, load_documents, report_dir, write_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect exact and near-duplicate Dental AI documents.")
    add_common_args(parser)
    args = parser.parse_args()

    reports = report_dir(args.report_dir)
    docs = load_documents(args.db)
    rows, _ = duplicate_document_groups(docs, sample_similarity=args.sample_similarity)
    write_csv(reports / "duplicate_documents.csv", rows)
    exact = len({row["duplicate_group_id"] for row in rows if row["match_type"] == "exact_file_hash"})
    near = len({row["duplicate_group_id"] for row in rows if row["match_type"] == "near_duplicate"})
    print(f"duplicate_documents.csv written to: {reports}")
    print(f"exact duplicate groups: {exact}")
    print(f"near duplicate groups: {near}")


if __name__ == "__main__":
    main()
