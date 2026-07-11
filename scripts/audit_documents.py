from __future__ import annotations

import argparse

from cleanup_audit_lib import (
    add_common_args,
    chunk_cleaning_rows,
    cleanup_summary,
    document_audit_rows,
    duplicate_chunk_rows,
    duplicate_document_groups,
    load_documents,
    print_summary,
    report_dir,
    write_csv,
    write_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run audit of Dental AI documents and chunks.")
    add_common_args(parser)
    args = parser.parse_args()

    reports = report_dir(args.report_dir)
    docs = load_documents(args.db)
    duplicate_doc_rows, duplicate_doc_ids = duplicate_document_groups(docs, sample_similarity=args.sample_similarity)
    audit_rows, removal_rows, metadata_rows = document_audit_rows(docs, duplicate_doc_ids)
    duplicate_chunk_rows_value, _ = duplicate_chunk_rows(docs)
    chunk_rows, noisy_removed = chunk_cleaning_rows(docs)
    summary = cleanup_summary(docs, audit_rows, duplicate_doc_rows, duplicate_chunk_rows_value, noisy_removed)

    write_csv(reports / "document_audit.csv", audit_rows)
    write_csv(reports / "duplicate_documents.csv", duplicate_doc_rows)
    write_csv(reports / "duplicate_chunks.csv", duplicate_chunk_rows_value)
    write_csv(reports / "removal_candidates.csv", removal_rows)
    write_csv(reports / "metadata_issues.csv", metadata_rows)
    write_csv(reports / "chunk_cleaning_dry_run.csv", chunk_rows)
    write_json(reports / "cleanup_summary.json", summary)

    print(f"Dry-run reports written to: {reports}")
    print_summary(summary)


if __name__ == "__main__":
    main()
