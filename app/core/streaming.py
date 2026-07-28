from __future__ import annotations

import json
import time
from typing import Any, AsyncGenerator

from app.core.config import get_settings
from app.core.logging import get_logger
from app.middleware.metrics import AGENT_GRAPH_FALLBACK_TOTAL

logger = get_logger(__name__)

# NOTE on citation verification and streaming (docs/GAP_AUDIT_PHASE0.md finding #10, #12):
# validate_citations() (the citation verifier) can only run once the full answer text
# exists, so it necessarily runs after every token has already been streamed to the
# client. If it trims an unsupported sentence, the live view the user watched will not
# retroactively change - but the canonical answer persisted to the database (and any
# reload of the conversation) reflects the verified/trimmed version. This mirrors the
# non-streaming graph path's behavior (which also verifies only the final text) and is a
# deliberate choice: for a medical-adjacent product we prioritize the persisted record
# being safety-checked over pixel-perfect stream/persisted-text parity. See ADR-0002.


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
    """Streaming counterpart of the LangGraph agent path in app/agent/graph.py.

    This reuses the same node functions (safety, memory, intent, query rewrite, retrieval,
    reranking, context building, self-check, citation verification, confidence, follow-up)
    so the two paths can't drift the way finding #10 described - the only thing streaming
    does differently is generate the answer token-by-token instead of in one shot, and
    skip the non-streaming path's trailing "Sources:" text block (streaming already has a
    dedicated 'sources' SSE event; appending a duplicate text block would be a UX
    regression that never existed here before).
    """
    settings = get_settings()

    yield f"data: {json.dumps({'type': 'start', 'session_id': session_id})}\n\n"

    from app.agent.state import AgentState
    from app.agent.nodes.safety import run_safety_check
    from app.agent.nodes.confidence import estimate_confidence
    from app.agent.nodes.follow_up import generate_follow_up_suggestions
    from app.agent.nodes.planner import build_context, rewrite_query, validate_citations
    from app.agent.graph import (
        _build_system_prompt,
        _build_user_prompt,
        load_memory_context,
        populate_sources_and_visuals,
        rerank_results,
        retrieve_chunks,
        retrieve_visuals,
        run_self_check_and_adjust_answer,
    )
    from app.agent.nodes.intent_classifier import classify_intent
    from app.services.llm import LLMGenerationError, LLMService, OllamaBusyError, OllamaCircuitOpenError
    from app.services.rag import RAGService

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

    try:
        run_safety_check(state)

        if not state.safety_check_passed or state.answer_mode == "emergency_triage":
            # Phase 5a: mirrors the non-streaming graph's short-circuit (see
            # app/agent/graph.py's _route_after_safety_check) - a red-flag emergency
            # skips retrieval/generation entirely rather than streaming a generated
            # answer, same as the safety-blocked case just below it.
            if not state.answer:
                state.answer = "I cannot process this request. Please ask a dental health question."
            yield f"data: {json.dumps({'type': 'content', 'text': state.answer})}\n\n"
            blocked_meta = json.dumps({
                'type': 'metadata_extended',
                'confidence_level': state.confidence_level if state.answer_mode == "emergency_triage" else 'blocked',
                'confidence_score': state.confidence_score if state.answer_mode == "emergency_triage" else 0,
                'explainability_notes': state.explainability_notes or ['Request blocked by safety system'],
                'follow_up_suggestions': [],
                'intent': state.intent,
                'sub_intent': state.sub_intent,
                'answer_mode': state.answer_mode or 'safety_blocked',
            })
            yield f"data: {blocked_meta}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'disclaimer': settings.medical_disclaimer if state.answer_mode == 'emergency_triage' else ''})}\n\n"
            yield "data: [DONE]\n\n"
            return

        load_memory_context(state)

        classify_intent(state)
        yield f"data: {json.dumps({'type': 'intent', 'intent': state.intent, 'simplify': state.simplify_for_patient})}\n\n"

        retrieval_start = time.perf_counter()
        yield f"data: {json.dumps({'type': 'thinking', 'detail': 'Searching knowledge base...'})}\n\n"

        rewrite_query(state)
        retrieve_chunks(state)
        retrieve_visuals(state)
        rerank_results(state)
        build_context(state)

        retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

        effective_chunks = state.reranked_chunks or state.retrieved_chunks
        chunk_count = len(effective_chunks)
        # Provisional: the authoritative mode is only known after generation + self-check +
        # citation verification, and is sent later via metadata_extended (finding #18).
        provisional_mode = "rag_grounded" if chunk_count else "general_fallback"

        yield f"data: {json.dumps({'type': 'thinking', 'detail': f'Found {chunk_count} sources. Generating answer...'})}\n\n"
        yield f"data: {json.dumps({'type': 'metadata', 'answer_mode': provisional_mode, 'source_count': chunk_count, 'retrieval_ms': retrieval_ms, 'intent': state.intent})}\n\n"

        system_prompt = _build_system_prompt(state)
        user_prompt = _build_user_prompt(state)

        from app.core.concurrency import get_ollama_gate
        gate = get_ollama_gate()
        if gate.is_saturated:
            # Explicit queued signal instead of silently blocking inside agenerate_stream()
            # while other requests hold every GPU inference slot (Phase 1).
            yield f"data: {json.dumps({'type': 'queued', 'queue_depth': gate.queue_depth})}\n\n"

        llm = LLMService()
        full_answer = ""
        generation_degraded = False
        try:
            async for token in llm.agenerate_stream(user_prompt, system_prompt=system_prompt):
                full_answer += token
                yield f"data: {json.dumps({'type': 'content', 'text': token})}\n\n"
        except (OllamaBusyError, OllamaCircuitOpenError) as exc:
            generation_degraded = True
            reason = "ollama_busy" if isinstance(exc, OllamaBusyError) else "ollama_circuit_open"
            logger.warning(
                f"streaming.generation_degraded reason={reason}",
                extra={"extra_data": {"user_id": user_id, "reason": reason}},
            )
            AGENT_GRAPH_FALLBACK_TOTAL.labels(reason=f"streaming_{reason}").inc()
            full_answer = (
                "The dental AI model is at capacity right now. Please try again in a moment."
            )
            state.answer_mode = "service_degraded"
            yield f"data: {json.dumps({'type': 'content', 'text': full_answer})}\n\n"
        except LLMGenerationError as exc:
            generation_degraded = True
            logger.warning(
                f"streaming.generation_failed error={exc}",
                extra={"extra_data": {"user_id": user_id}},
            )
            AGENT_GRAPH_FALLBACK_TOTAL.labels(reason="streaming_llm_error").inc()
            fallback = None
            try:
                rag = RAGService()
                fallback = rag.generate_general_fallback_answer(question, user_role=user_role)
            except Exception:
                fallback = None
            if fallback:
                full_answer = fallback
                state.answer_mode = "general_fallback"
            else:
                full_answer = settings.medical_disclaimer
                state.answer_mode = "service_unavailable"
            yield f"data: {json.dumps({'type': 'content', 'text': full_answer})}\n\n"

        state.answer = full_answer
        if not generation_degraded:
            state.answer_mode = provisional_mode
            run_self_check_and_adjust_answer(state)
            populate_sources_and_visuals(state)
            validate_citations(state)

        try:
            from app.services.rag import enforce_safety_note
            state.answer = enforce_safety_note(state.answer, state.question)
        except Exception:
            pass

        estimate_confidence(state)
        generate_follow_up_suggestions(state)

        yield f"data: {json.dumps({'type': 'sources', 'sources': state.sources, 'visuals': state.visuals})}\n\n"

        extended_meta = json.dumps({
            'type': 'metadata_extended',
            'confidence_level': state.confidence_level,
            'confidence_score': round(state.confidence_score, 2),
            'explainability_notes': state.explainability_notes,
            'follow_up_suggestions': state.follow_up_suggestions,
            'intent': state.intent,
            'sub_intent': state.sub_intent,
            'answer_mode': state.answer_mode,
        })
        yield f"data: {extended_meta}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'disclaimer': settings.medical_disclaimer})}\n\n"

    except Exception as exc:
        logger.error(f"Streaming chat failed: {exc}", exc_info=True)
        AGENT_GRAPH_FALLBACK_TOTAL.labels(reason=f"streaming_{exc.__class__.__name__}").inc()
        yield f"data: {json.dumps({'type': 'error', 'detail': 'An error occurred processing your request.'})}\n\n"

    yield "data: [DONE]\n\n"


def format_sse_event(event_type: str, data: dict[str, Any]) -> str:
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"
