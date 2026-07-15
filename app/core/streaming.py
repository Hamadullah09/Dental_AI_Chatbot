from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncGenerator

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def stream_chat_response(
    question: str,
    session_id: str | None,
    user_id: str,
    user_role: str,
    document_id: str | None = None,
    search_web: bool = False,
    top_k: int | None = None,
    filters: dict[str, Any] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
) -> AsyncGenerator[str, None]:
    settings = get_settings()

    yield f"data: {json.dumps({'type': 'start', 'session_id': session_id})}\n\n"

    try:
        from app.agent.graph import build_langgraph
        from app.agent.state import AgentState

        state = AgentState(
            question=question,
            session_id=session_id,
            user_id=user_id,
            user_role=user_role,
            document_id=document_id,
            search_web=search_web,
            top_k=top_k,
            filters=filters or {},
            conversation_history=conversation_history or [],
        )

        yield f"data: {json.dumps({'type': 'thinking', 'detail': 'Analyzing your question...'})}\n\n"

        graph = build_langgraph()
        start = time.perf_counter()
        result = await asyncio.to_thread(graph.invoke, state)
        duration_ms = (time.perf_counter() - start) * 1000

        if isinstance(result, AgentState):
            answer = result.answer
            sources = result.sources if isinstance(result.sources, list) else []
            visuals = result.visuals if isinstance(result.visuals, list) else []
            answer_mode = result.answer_mode
            trace = result.trace_log
        else:
            answer = result.get("answer", "")
            sources = result.get("sources", [])
            visuals = result.get("visuals", [])
            answer_mode = result.get("answer_mode", "rag_grounded")
            trace = result.get("trace_log", [])

        yield f"data: {json.dumps({'type': 'metadata', 'answer_mode': answer_mode, 'source_count': len(sources), 'visual_count': len(visuals), 'duration_ms': duration_ms})}\n\n"

        chunk_size = settings.streaming_chunk_size
        for i in range(0, len(answer), chunk_size):
            chunk = answer[i:i + chunk_size]
            yield f"data: {json.dumps({'type': 'content', 'text': chunk})}\n\n"

        source_data = [
            {
                "source_type": s.source_type if hasattr(s, "source_type") else s.get("source_type", "pdf"),
                "document_name": s.document_name if hasattr(s, "document_name") else s.get("document_name", "Unknown"),
                "page_number": s.page_number if hasattr(s, "page_number") else s.get("page_number"),
                "score": s.score if hasattr(s, "score") else s.get("score"),
            }
            for s in sources[:5]
        ]

        visual_data = [
            {
                "visual_id": v.visual_id if hasattr(v, "visual_id") else v.get("visual_id", ""),
                "document_name": v.document_name if hasattr(v, "document_name") else v.get("document_name", "Unknown"),
                "page_number": v.page_number if hasattr(v, "page_number") else v.get("page_number"),
                "image_url": v.image_url if hasattr(v, "image_url") else v.get("image_url", ""),
                "caption_text": v.caption_text if hasattr(v, "caption_text") else v.get("caption_text"),
            }
            for v in visuals[:3]
        ]

        yield f"data: {json.dumps({'type': 'sources', 'sources': source_data, 'visuals': visual_data})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'disclaimer': settings.medical_disclaimer})}\n\n"

    except Exception as exc:
        logger.error(f"Streaming chat failed: {exc}")
        yield f"data: {json.dumps({'type': 'error', 'detail': 'An error occurred processing your request.'})}\n\n"

    yield "data: [DONE]\n\n"


def format_sse_event(event_type: str, data: dict[str, Any]) -> str:
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"
