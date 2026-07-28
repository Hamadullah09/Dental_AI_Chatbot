from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.deps import require_admin
from app.models import AuditLog, Document, DocumentIngestionLog, DocumentStatus, DocumentType, Feedback, Message, ReviewStatus, TrustLevel, User
from app.schemas import DatasetGenerationRequest, DatasetGenerationStatus, DocumentIngestionLogRead, DocumentRead, FeedbackReviewItem, FeedbackReviewResult
from app.services.dataset_generation import REVIEW_CSV_PATH, export_review_csv, generate_dataset_background, read_dataset_status
from app.services.documents import save_upload
from app.services.ingestion import IngestionService


router = APIRouter(prefix="/admin", tags=["admin"])


def ingest_document_background(document_id: str) -> None:
    """Last-resort fallback if app.workers.tasks.start_ingestion() itself raises - see
    that function for the primary enqueue-or-run-inline path (Phase 4)."""
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if not document:
            return
        try:
            IngestionService().ingest_document(db, document)
        except Exception:
            # The ingestion service persists failed status and error details.
            return


def start_ingestion(background_tasks: BackgroundTasks, document_id: str) -> None:
    try:
        from app.workers.tasks import start_ingestion as _start_ingestion
        _start_ingestion(
            document_id,
            inline_fallback=lambda: background_tasks.add_task(ingest_document_background, document_id),
        )
    except Exception:
        background_tasks.add_task(ingest_document_background, document_id)


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
    settings = get_settings()
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
        "provider": settings.dataset_llm_provider,
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


@router.get("/documents/{document_id}/logs", response_model=list[DocumentIngestionLogRead])
def list_document_ingestion_logs(
    document_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[DocumentIngestionLog]:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return (
        db.query(DocumentIngestionLog)
        .filter(DocumentIngestionLog.document_id == document_id)
        .order_by(DocumentIngestionLog.created_at.desc())
        .limit(100)
        .all()
    )


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
        document.ingestion_progress = 0
        document.ingestion_step = "Queued"
        document.error_message = None
        db.commit()
        db.refresh(document)
        start_ingestion(background_tasks, document.id)
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
        document.ingestion_progress = 0
        document.ingestion_step = "Queued"
        document.ingestion_completed_at = None
        db.commit()
        db.refresh(document)
        start_ingestion(background_tasks, document.id)
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

    try:
        from app.services.retrieval_cache import bump_generation
        bump_generation()
    except Exception:
        pass


@router.post("/users/{user_id}/revoke-sessions", status_code=status.HTTP_204_NO_CONTENT)
def revoke_user_sessions(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> None:
    """Sign a user out everywhere: revokes every stored refresh token and blocklists every
    access token issued before now (Phase 2 - incident response for a compromised
    account). Access tokens are stateless JWTs, so without this a compromised token would
    stay valid until its natural expiry regardless of anything else we do."""
    from datetime import datetime, timezone

    from app.core.token_blocklist import revoke_all_tokens_for_user
    from app.models import RefreshToken

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked.is_(False),
    ).update({"revoked": True, "revoked_at": datetime.now(timezone.utc)})
    db.commit()

    revoke_all_tokens_for_user(user_id)

    log = AuditLog(
        user_id=admin.id,
        action="revoke_user_sessions",
        resource_type="user",
        resource_id=user_id,
    )
    db.add(log)
    db.commit()


@router.get("/feedback", response_model=FeedbackReviewResult)
def list_feedback_for_review(
    max_rating: int | None = Query(None, ge=1, le=5, description="Only feedback at or below this rating (default: all)"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> FeedbackReviewResult:
    """Feedback review queue (Phase 5): feedback could always be submitted via
    POST /api/feedback, but nothing let anyone actually see it - low ratings had no way
    to surface for review or feed into retrieval/prompt tuning. Ordered worst-first by
    default (max_rating unset shows everything, still worst-first) so the most
    actionable items are at the top."""
    from app.models import MessageRole

    query = db.query(Feedback)
    if max_rating is not None:
        query = query.filter(Feedback.rating <= max_rating)

    total = query.count()
    total_pages = (total + limit - 1) // limit if total else 0
    offset = (page - 1) * limit

    rows = (
        query.order_by(Feedback.rating.asc(), Feedback.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items: list[FeedbackReviewItem] = []
    for feedback in rows:
        assistant_message = db.get(Message, feedback.message_id)
        question = None
        if assistant_message:
            preceding = (
                db.query(Message)
                .filter(
                    Message.session_id == assistant_message.session_id,
                    Message.role == MessageRole.user,
                    Message.created_at <= assistant_message.created_at,
                )
                .order_by(Message.created_at.desc())
                .first()
            )
            question = preceding.content if preceding else None
        user = db.get(User, feedback.user_id)
        items.append(
            FeedbackReviewItem(
                id=feedback.id,
                rating=feedback.rating,
                comment=feedback.comment,
                created_at=feedback.created_at,
                message_id=feedback.message_id,
                question=question,
                answer=assistant_message.content if assistant_message else None,
                user_id=feedback.user_id,
                user_email=user.email if user else None,
            )
        )

    all_ratings = [row.rating for row in db.query(Feedback.rating).all()]
    average_rating = sum(all_ratings) / len(all_ratings) if all_ratings else None

    return FeedbackReviewResult(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
        average_rating=average_rating,
    )
