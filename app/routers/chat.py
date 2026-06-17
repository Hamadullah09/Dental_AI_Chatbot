import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models import ChatSession, Feedback, Message, MessageRole, User
from app.schemas import ChatRequest, ChatResponse, ChatSessionRead, FeedbackCreate, FeedbackRead, MessageRead
from app.services.rag import RAGService


router = APIRouter(tags=["chat"])


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
