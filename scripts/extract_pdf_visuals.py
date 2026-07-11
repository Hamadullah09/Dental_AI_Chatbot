from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal, init_db
from app.models import Document, DocumentStatus, DocumentVisual
from app.services.visuals import extract_and_index_document_visuals


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract and index visual assets from ingested PDFs.")
    parser.add_argument("--document-id", help="Process one document id. Default processes all ready documents.")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of documents.")
    parser.add_argument("--force", action="store_true", help="Re-extract documents even when visuals already exist.")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as db:
        query = db.query(Document).filter(Document.status == DocumentStatus.ready)
        if args.document_id:
            query = query.filter(Document.id == args.document_id)
        documents = query.order_by(Document.created_at.desc()).all()
        if args.limit:
            documents = documents[: args.limit]
        total_visuals = 0
        skipped = 0
        for document in documents:
            if not args.force:
                existing = db.query(DocumentVisual).filter(DocumentVisual.document_id == document.id).count()
                if existing:
                    skipped += 1
                    print(f"Skipping existing visuals: {document.original_filename} ({existing})")
                    continue
            print(f"Extracting visuals: {document.original_filename} ({document.id})")
            count = extract_and_index_document_visuals(
                db,
                document,
                log=lambda message, level="info": print(f"  {level.upper()}: {message}"),
            )
            db.commit()
            total_visuals += count
            print(f"  visuals indexed: {count}")
        print(f"Done. Documents: {len(documents)}, skipped: {skipped}, visuals indexed: {total_visuals}")


if __name__ == "__main__":
    main()
