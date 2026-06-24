import json

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.deps import get_current_user
from app.models import ChatSession, Document, DocumentStatus, DocumentType, Feedback, Message, MessageRole, ReviewStatus, TrustLevel, User
from app.schemas import ChatRequest, ChatResponse, ChatSessionRead, DocumentRead, FeedbackCreate, FeedbackRead, MessageRead
from app.services.documents import save_upload
from app.services.ingestion import IngestionService
from app.services.rag import RAGService


router = APIRouter(tags=["chat"])


def ingest_user_document_background(document_id: str) -> None:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if not document:
            return
        try:
            IngestionService().ingest_document(db, document)
        except Exception:
            return


def _sources_to_json(sources: list) -> str:
    return json.dumps([source.model_dump() for source in sources])


def _message_read(message: Message) -> MessageRead:
    sources = json.loads(message.sources_json) if message.sources_json else []
    return MessageRead(
        id=message.id,
        role=message.role.value,
        content=message.content,
        sources=sources,
        created_at=message.created_at,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    session = db.get(ChatSession, payload.session_id) if payload.session_id else None
    if session and session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if not session:
        session = ChatSession(user_id=current_user.id, title=question[:80])
        db.add(session)
        db.commit()
        db.refresh(session)

    document = None
    if payload.document_id:
        document = db.get(Document, payload.document_id)
        if not document or document.uploaded_by != current_user.id:
            raise HTTPException(status_code=404, detail="Uploaded document not found")
        if document.status != DocumentStatus.ready:
            raise HTTPException(status_code=409, detail="Document is still being processed. Please try again when ingestion is ready.")

    db.add(Message(session_id=session.id, role=MessageRole.user, content=question))
    service = RAGService()
    answer, sources = service.answer(
        question,
        top_k=payload.top_k,
        filters={
            "document_types": [item.value for item in payload.document_types] if payload.document_types else None,
            "trust_levels": [item.value for item in payload.trust_levels] if payload.trust_levels else None,
            "review_status": payload.review_status.value if payload.review_status else None,
            "min_year": payload.min_year,
            "user_role": current_user.role.value,
            "document_id": document.id if document else None,
            "search_web": payload.search_web,
        },
    )
    assistant_message = Message(
        session_id=session.id,
        role=MessageRole.assistant,
        content=answer,
        sources_json=_sources_to_json(sources),
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return ChatResponse(
        answer=answer,
        session_id=session.id,
        message_id=assistant_message.id,
        sources=sources,
        disclaimer=get_settings().medical_disclaimer,
    )


@router.post("/chat/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_chat_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    book_title: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    try:
        document = save_upload(
            db,
            file,
            current_user,
            book_title=book_title,
            document_type=DocumentType.other,
            trust_level=TrustLevel.medium,
            review_status=ReviewStatus.approved,
        )
        document.status = DocumentStatus.processing
        document.ingestion_progress = 0
        document.ingestion_step = "Queued"
        db.commit()
        db.refresh(document)
        background_tasks.add_task(ingest_user_document_background, document.id)
        return document
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Document upload failed: {exc}")


@router.get("/chat/documents/{document_id}", response_model=DocumentRead)
def get_chat_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    document = db.get(Document, document_id)
    if not document or document.uploaded_by != current_user.id:
        raise HTTPException(status_code=404, detail="Uploaded document not found")
    return document


@router.get("/chat/sessions", response_model=list[ChatSessionRead])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChatSessionRead]:
    sessions = (
        db.query(ChatSession)
        .options(selectinload(ChatSession.messages))
        .filter(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return [
        ChatSessionRead(
            id=session.id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
            messages=[_message_read(message) for message in session.messages],
        )
        for session in sessions
    ]


@router.post("/feedback", response_model=FeedbackRead)
def create_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Feedback:
    message = db.get(Message, payload.message_id)
    if not message or message.session.user_id != current_user.id or message.role != MessageRole.assistant:
        raise HTTPException(status_code=404, detail="Assistant message not found")
    feedback = Feedback(
        message_id=message.id,
        user_id=current_user.id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback
