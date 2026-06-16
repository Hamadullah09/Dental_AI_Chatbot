"""Offline ingestion entry point for PDFs in knowledge_base/."""

from pathlib import Path

from app.core.database import SessionLocal, init_db
from app.models import Document, DocumentStatus
from app.services.ingestion import IngestionService


KNOWLEDGE_BASE_DIR = Path("knowledge_base")


def main() -> None:
    init_db()
    service = IngestionService()
    service.ensure_collection()
    pdfs = sorted(KNOWLEDGE_BASE_DIR.glob("*.pdf"))
    if not pdfs:
        print("No PDFs found in knowledge_base/.")
        return

    with SessionLocal() as db:
        total_chunks = 0
        for pdf_path in pdfs:
            document = Document(
                filename=pdf_path.name,
                original_filename=pdf_path.name,
                content_type="application/pdf",
                storage_path=str(pdf_path),
                status=DocumentStatus.uploaded,
            )
            db.add(document)
            db.commit()
            db.refresh(document)
            print(f"Ingesting {pdf_path} ...")
            chunk_count = service.ingest_document(db, document)
            print(f"Uploaded {chunk_count} chunks from {pdf_path.name}")
            total_chunks += chunk_count
        print(f"Finished ingesting {total_chunks} chunks across {len(pdfs)} files.")


if __name__ == "__main__":
    main()
