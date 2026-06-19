from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.deps import require_admin
from app.models import Document, DocumentStatus, DocumentType, ReviewStatus, TrustLevel, User
from app.schemas import DatasetGenerationRequest, DatasetGenerationStatus, DocumentRead
from app.services.dataset_generation import REVIEW_CSV_PATH, export_review_csv, generate_dataset_background, read_dataset_status
from app.services.documents import save_upload
from app.services.ingestion import IngestionService


router = APIRouter(prefix="/admin", tags=["admin"])


def ingest_document_background(document_id: str) -> None:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if not document:
            return
        try:
            IngestionService().ingest_document(db, document)
        except Exception:
            # The ingestion service persists failed status and error details.
            return


@router.get("/dataset/status", response_model=DatasetGenerationStatus)
def dataset_generation_status(
    _: User = Depends(require_admin),
) -> dict:
    return read_dataset_status()


@router.post("/dataset/generate", response_model=DatasetGenerationStatus, status_code=status.HTTP_202_ACCEPTED)
def generate_dataset(
    request: DatasetGenerationRequest,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_admin),
) -> dict:
    current = read_dataset_status()
    if current.get("state") == "running":
        raise HTTPException(status_code=409, detail="Dataset generation is already running.")
    background_tasks.add_task(
        generate_dataset_background,
        limit=request.limit,
        examples_per_chunk=request.examples_per_chunk,
        min_quality=request.min_quality,
        include_noisy=request.include_noisy,
        document_id=request.document_id,
    )
    return {
        "state": "queued",
        "processed_chunks": 0,
        "generated_items": 0,
        "skipped_chunks": 0,
        "duplicate_chunks": 0,
        "removed_existing_rows": 0,
        "document_id": request.document_id,
        "document_name": None,
        "output_path": "draft_dental_qa.jsonl",
        "skipped_path": "skipped_chunks.jsonl",
        "review_csv_path": "Database Q&A.csv",
        "message": "Dataset generation queued. Status will update as chunks are processed.",
    }


@router.get("/dataset/download")
def download_dataset_review_csv(
    _: User = Depends(require_admin),
) -> FileResponse:
    try:
        path = export_review_csv()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No draft Q&A dataset has been generated yet.")
    if not path.exists() or path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="Review CSV is not available yet.")
    return FileResponse(
        path=path,
        media_type="text/csv",
        filename=REVIEW_CSV_PATH.name,
    )


@router.get("/documents", response_model=list[DocumentRead])
def list_documents(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[Document]:
    return db.query(Document).order_by(Document.created_at.desc()).all()


@router.post("/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    book_title: str | None = Form(None),
    author_or_source: str | None = Form(None),
    year: int | None = Form(None),
    edition: str | None = Form(None),
    document_type: DocumentType = Form(DocumentType.textbook),
    trust_level: TrustLevel = Form(TrustLevel.high),
    specialty: str | None = Form(None),
    language: str | None = Form("English"),
    review_status: ReviewStatus = Form(ReviewStatus.approved),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Document:
    try:
        document = save_upload(
            db,
            file,
            current_user,
            book_title=book_title,
            author_or_source=author_or_source,
            year=year,
            edition=edition,
            document_type=document_type,
            trust_level=trust_level,
            specialty=specialty,
            language=language,
            review_status=review_status,
        )
        document.status = DocumentStatus.processing
        db.commit()
        db.refresh(document)
        background_tasks.add_task(ingest_document_background, document.id)
        return document
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Document upload failed: {exc}")


@router.post("/documents/{document_id}/reingest", response_model=DocumentRead)
def reingest_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        document.status = DocumentStatus.processing
        document.error_message = None
        db.commit()
        db.refresh(document)
        background_tasks.add_task(ingest_document_background, document.id)
        return document
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Document re-ingest failed: {exc}")


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        IngestionService().delete_document_vectors(document.id)
    except Exception:
        pass
    storage_path = Path(document.storage_path)
    db.delete(document)
    db.commit()
    if storage_path.exists():
        storage_path.unlink()
