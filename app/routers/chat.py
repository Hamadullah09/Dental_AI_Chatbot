import json

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.core.logging import get_logger, user_id_var
from app.core.streaming import stream_chat_response
from app.deps import get_current_user
from app.models import ChatSession, Document, DocumentStatus, DocumentType, Feedback, Message, MessageRole, ReviewStatus, TrustLevel, User
from app.schemas import ChatRequest, ChatResponse, ChatSessionRead, DocumentRead, FeedbackCreate, FeedbackRead, MessageRead
from app.services.documents import save_upload
from app.services.ingestion import IngestionService
from app.services.rag import RAGService
from app.middleware.metrics import CHAT_QUERIES, LLM_LATENCY, RETRIEVAL_LATENCY
import time


logger = get_logger(__name__)
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


def _sources_to_json(sources: list, visuals: list | None = None) -> str:
    return json.dumps(
        {
            "sources": [s.model_dump() if hasattr(s, "model_dump") else s for s in sources],
            "visuals": [v.model_dump() if hasattr(v, "model_dump") else v for v in (visuals or [])],
        }
    )


def _message_read(message: Message) -> MessageRead:
    stored = json.loads(message.sources_json) if message.sources_json else []
    if isinstance(stored, dict):
        sources = stored.get("sources") or []
        visuals = stored.get("visuals") or []
    else:
        sources = stored
        visuals = []
    return MessageRead(
        id=message.id,
        role=message.role.value,
        content=message.content,
        sources=sources,
        visuals=visuals,
        created_at=message.created_at,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    user_id_var.set(current_user.id)
    start = time.perf_counter()

    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    session = db.get(ChatSession, payload.session_id) if payload.session_id else None
    if session and session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if session and session.archived:
        session.archived = False
        db.commit()
        db.refresh(session)
    if not session:
        session = ChatSession(user_id=current_user.id, title=question[:80])
        db.add(session)
        db.commit()
        db.refresh(session)

    history_messages = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.created_at.desc())
        .limit(get_settings().conversation_history_limit)
        .all()
    )
    conversation_history = [
        {"role": message.role.value, "content": message.content}
        for message in reversed(history_messages)
    ]

    document = None
    if payload.document_id:
        document = db.get(Document, payload.document_id)
        if not document or document.uploaded_by != current_user.id:
            raise HTTPException(status_code=404, detail="Uploaded document not found")
        if document.status != DocumentStatus.ready:
            raise HTTPException(status_code=409, detail="Document is still being processed. Please try again when ingestion is ready.")

    db.add(Message(session_id=session.id, role=MessageRole.user, content=question))
    db.commit()

    retrieval_start = time.perf_counter()
    try:
        from app.agent.graph import build_langgraph
        from app.agent.state import AgentState

        state = AgentState(
            question=question,
            session_id=session.id,
            user_id=current_user.id,
            user_role=current_user.role.value,
            document_id=document.id if document else None,
            search_web=payload.search_web,
            top_k=payload.top_k,
            filters={
                "document_types": [item.value for item in payload.document_types] if payload.document_types else None,
                "trust_levels": [item.value for item in payload.trust_levels] if payload.trust_levels else None,
                "review_status": payload.review_status.value if payload.review_status else None,
                "min_year": payload.min_year,
                "user_role": current_user.role.value,
                "document_id": document.id if document else None,
                "search_web": payload.search_web,
                "conversation_history": conversation_history,
            },
            conversation_history=conversation_history,
        )

        graph = build_langgraph()
        result = graph.invoke(state)

        if isinstance(result, AgentState):
            answer = result.answer
            sources = result.sources
            visuals = result.visuals or []
            answer_mode = result.answer_mode
        elif isinstance(result, dict):
            answer = result.get("answer", "")
            sources = result.get("sources", [])
            visuals = result.get("visuals", [])
            answer_mode = result.get("answer_mode", "rag_grounded")
        else:
            rag = RAGService()
            rag_result = rag.answer(question, top_k=payload.top_k, filters={})
            answer, sources = rag_result
            answer_mode = "rag_grounded" if sources else "general_fallback"
            visuals = []

    except Exception:
        rag = RAGService()
        rag_result = rag.answer(
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
                "conversation_history": conversation_history,
            },
        )
        if hasattr(rag_result, "answer"):
            answer = rag_result.answer
            sources = rag_result.sources
            answer_mode = rag_result.answer_mode
            visuals = rag_result.visuals or []
        else:
            answer, sources = rag_result
            answer_mode = "rag_grounded" if sources else "general_fallback"
            visuals = []

    retrieval_duration = (time.perf_counter() - retrieval_start) * 1000
    RETRIEVAL_LATENCY.labels(mode=answer_mode).observe(retrieval_duration / 1000)

    if answer_mode == "service_unavailable":
        raise HTTPException(status_code=503, detail="The dental AI model did not respond in time. Please try again.")

    assistant_message = Message(
        session_id=session.id,
        role=MessageRole.assistant,
        content=answer,
        sources_json=_sources_to_json(sources, visuals),
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    total_duration = (time.perf_counter() - start) * 1000
    CHAT_QUERIES.labels(answer_mode=answer_mode).inc()
    logger.info(
        f"Chat completed: {total_duration:.0f}ms, mode={answer_mode}, sources={len(sources)}",
        extra={"extra_data": {"user_id": current_user.id, "duration_ms": total_duration, "answer_mode": answer_mode}},
    )

    return ChatResponse(
        answer=answer,
        session_id=session.id,
        message_id=assistant_message.id,
        sources=sources,
        visuals=visuals,
        answer_mode=answer_mode,
        disclaimer=get_settings().medical_disclaimer,
    )


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    user_id_var.set(current_user.id)

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

    history_messages = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.created_at.desc())
        .limit(get_settings().conversation_history_limit)
        .all()
    )
    conversation_history = [
        {"role": message.role.value, "content": message.content}
        for message in reversed(history_messages)
    ]

    document = None
    if payload.document_id:
        document = db.get(Document, payload.document_id)
        if not document or document.uploaded_by != current_user.id:
            raise HTTPException(status_code=404, detail="Uploaded document not found")
        if document.status != DocumentStatus.ready:
            raise HTTPException(status_code=409, detail="Document is still being processed.")

    db.add(Message(session_id=session.id, role=MessageRole.user, content=question))
    db.commit()

    filters = {
        "document_types": [item.value for item in payload.document_types] if payload.document_types else None,
        "trust_levels": [item.value for item in payload.trust_levels] if payload.trust_levels else None,
        "review_status": payload.review_status.value if payload.review_status else None,
        "min_year": payload.min_year,
        "user_role": current_user.role.value,
        "document_id": document.id if document else None,
        "search_web": payload.search_web,
        "conversation_history": conversation_history,
    }

    async def event_generator():
        full_answer = ""
        final_sources = []
        final_visuals = []
        final_mode = "rag_grounded"

        async for chunk in stream_chat_response(
            question=question,
            session_id=session.id,
            user_id=current_user.id,
            user_role=current_user.role.value,
            document_id=document.id if document else None,
            search_web=payload.search_web,
            top_k=payload.top_k,
            filters=filters,
            conversation_history=conversation_history,
        ):
            yield chunk

            if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                try:
                    event = json.loads(chunk[6:])
                    if event.get("type") == "content":
                        full_answer += event.get("text", "")
                    elif event.get("type") == "sources":
                        final_sources = event.get("sources", [])
                        final_visuals = event.get("visuals", [])
                    elif event.get("type") == "metadata":
                        final_mode = event.get("answer_mode", "rag_grounded")
                except json.JSONDecodeError:
                    pass

        if full_answer:
            with SessionLocal() as save_db:
                save_db.add(Message(
                    session_id=session.id,
                    role=MessageRole.assistant,
                    content=full_answer,
                    sources_json=json.dumps({"sources": final_sources, "visuals": final_visuals}),
                ))
                save_db.commit()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
        .filter(ChatSession.user_id == current_user.id, ChatSession.archived.is_(False))
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return [
        ChatSessionRead(
            id=session.id,
            title=session.title,
            archived=session.archived,
            created_at=session.created_at,
            updated_at=session.updated_at,
            messages=[_message_read(message) for message in session.messages],
        )
        for session in sessions
    ]


@router.post("/chat/sessions/{session_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
def archive_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    session = db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    session.archived = True
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/chat/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    session = db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    db.delete(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
