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
        from app.agent.state import AgentState
        from app.agent.nodes.safety import run_safety_check
        from app.agent.nodes.intent_classifier import classify_intent
        from app.agent.nodes.confidence import estimate_confidence
        from app.agent.nodes.follow_up import generate_follow_up_suggestions
        from app.services.rag import RAGService, rewrite_query_for_retrieval

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

        run_safety_check(state)

        if not state.safety_check_passed:
            if not state.answer:
                state.answer = "I cannot process this request. Please ask a dental health question."
            yield f"data: {json.dumps({'type': 'content', 'text': state.answer})}\n\n"
            blocked_meta = json.dumps({
                'type': 'metadata_extended',
                'confidence_level': 'blocked',
                'confidence_score': 0,
                'explainability_notes': ['Request blocked by safety system'],
                'follow_up_suggestions': [],
                'intent': state.intent,
                'sub_intent': state.sub_intent,
            })
            yield f"data: {blocked_meta}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'disclaimer': ''})}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            from app.services.memory import MemoryService
            mem_svc = MemoryService()
            memory_text = mem_svc.format_memory_for_prompt(user_id)
            if memory_text:
                state.memory_context = memory_text
            mem_svc.track_topic(user_id, question)
        except Exception:
            pass

        classify_intent(state)
        yield f"data: {json.dumps({'type': 'intent', 'intent': state.intent, 'simplify': state.simplify_for_patient})}\n\n"

        retrieval_start = time.perf_counter()
        rag = RAGService()
        query = state.question
        retrieval_question = rewrite_query_for_retrieval(query) if settings.enable_query_rewriting else query
        effective_top_k = min(5, max(3, top_k or settings.retrieval_top_k))

        yield f"data: {json.dumps({'type': 'thinking', 'detail': 'Searching knowledge base...'})}\n\n"

        chunks = rag.retrieve(retrieval_question, top_k=effective_top_k, filters=filters or {})

        state.retrieved_chunks = [
            {
                "text": chunk.text,
                "citation": {
                    "source_type": chunk.citation.source_type,
                    "document_id": chunk.citation.document_id,
                    "document_name": chunk.citation.document_name,
                    "page_number": chunk.citation.page_number,
                    "chunk_index": chunk.citation.chunk_index,
                    "score": chunk.citation.score,
                },
                "vector_score": chunk.vector_score,
                "keyword_score": chunk.keyword_score,
                "rerank_score": chunk.rerank_score,
            }
            for chunk in chunks
        ]

        retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

        context_parts = []
        for i, chunk in enumerate(chunks[:5]):
            citation = chunk.citation
            doc_name = citation.document_name or "Unknown"
            page = citation.page_number
            page_str = f" (p. {page})" if page else ""
            context_parts.append(f"[Source {i+1}: {doc_name}{page_str}]\n{chunk.text}")

        context_text = "\n\n---\n\n".join(context_parts)

        system_prompt = _build_streaming_system_prompt(state, context_text, settings)
        user_prompt = _build_streaming_user_prompt(question, conversation_history)

        yield f"data: {json.dumps({'type': 'thinking', 'detail': f'Found {len(chunks)} sources. Generating answer...'})}\n\n"
        yield f"data: {json.dumps({'type': 'metadata', 'answer_mode': 'rag_grounded', 'source_count': len(chunks), 'retrieval_ms': retrieval_ms, 'intent': state.intent})}\n\n"

        from app.services.llm import LLMService
        llm = LLMService()
        full_answer = ""
        try:
            for token in llm.generate_stream(user_prompt, system_prompt=system_prompt):
                full_answer += token
                yield f"data: {json.dumps({'type': 'content', 'text': token})}\n\n"
        except Exception:
            fallback = rag.generate_general_fallback_answer(question, user_role=user_role)
            if fallback:
                full_answer = fallback
                yield f"data: {json.dumps({'type': 'content', 'text': fallback})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'content', 'text': settings.medical_disclaimer})}\n\n"

        state.answer = full_answer
        state.answer_mode = "rag_grounded" if chunks else "general_fallback"

        for chunk in chunks[:5]:
            state.sources.append({
                "source_type": chunk.citation.source_type,
                "document_name": chunk.citation.document_name or "Unknown",
                "page_number": chunk.citation.page_number,
                "score": chunk.citation.score,
            })

        estimate_confidence(state)
        generate_follow_up_suggestions(state)

        source_data = [
            {
                "source_type": chunk.citation.source_type,
                "document_name": chunk.citation.document_name or "Unknown",
                "page_number": chunk.citation.page_number,
                "score": chunk.citation.score,
            }
            for chunk in chunks[:5]
        ]

        yield f"data: {json.dumps({'type': 'sources', 'sources': source_data, 'visuals': []})}\n\n"

        extended_meta = json.dumps({
            'type': 'metadata_extended',
            'confidence_level': state.confidence_level,
            'confidence_score': round(state.confidence_score, 2),
            'explainability_notes': state.explainability_notes,
            'follow_up_suggestions': state.follow_up_suggestions,
            'intent': state.intent,
            'sub_intent': state.sub_intent,
        })
        yield f"data: {extended_meta}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'disclaimer': settings.medical_disclaimer})}\n\n"

    except Exception as exc:
        logger.error(f"Streaming chat failed: {exc}")
        yield f"data: {json.dumps({'type': 'error', 'detail': 'An error occurred processing your request.'})}\n\n"

    yield "data: [DONE]\n\n"


def _build_streaming_system_prompt(state: AgentState, context_text: str, settings: Any) -> str:
    base = (
        "You are DentalGPT, an expert dental AI assistant. You provide accurate, evidence-based "
        "dental information grounded in the provided context. Always cite your sources using [Source N] format. "
        "Never provide medical advice that replaces professional dental consultation. "
        "Include the medical disclaimer at the end of every response.\n\n"
        f"Medical Disclaimer: {settings.medical_disclaimer}\n\n"
        "Response Guidelines:\n"
        "- Start with a direct, concise answer in 1-3 sentences\n"
        "- Use **bold** for important dental terms, symptoms, and warnings\n"
        "- Use markdown headings (##) for major sections\n"
        "- Use bullet points for lists of symptoms, causes, or steps\n"
        "- Keep paragraphs short (2-4 sentences max)\n"
        "- Always include [Source N] citations for factual claims\n"
        "- End with appropriate safety/consultation note\n\n"
    )

    if state.intent == "emergency":
        base += "IMPORTANT: This appears urgent. Start with URGENT: and emphasize seeking immediate care.\n\n"
    elif state.intent == "image_analysis":
        base += "Describe observable findings without certainty. Always recommend professional evaluation.\n\n"
    elif state.intent == "symptom":
        base += "Explain causes, when to see a dentist, and self-care tips. Recommend professional evaluation.\n\n"
    elif state.intent == "treatment":
        base += "Explain procedures, outcomes, recovery, risks, and alternatives.\n\n"
    elif state.intent == "patient_education":
        base += "Use PLAIN LANGUAGE. Define terms. Use analogies. Keep it simple for patient understanding.\n\n"
    elif state.intent == "clinical_decision":
        base += "Provide evidence-based recommendations for dental professionals. Discuss differentials and guidelines.\n\n"
    elif state.intent == "research":
        base += "Summarize evidence, mention study types, note evidence levels.\n\n"
    elif state.intent == "prescription_explain":
        base += "Explain medication use, side effects, precautions. Warn against self-prescribing.\n\n"

    if state.simplify_for_patient:
        base += "Use SIMPLE LANGUAGE. Define technical terms. Use analogies.\n\n"

    try:
        from app.services.rag import role_behavior_instruction
        base += role_behavior_instruction(state.user_role) + "\n\n"
    except Exception:
        pass

    if context_text:
        base += f"Context from dental knowledge base:\n{context_text}\n\n"

    if state.memory_context:
        base += f"User context:\n{state.memory_context}\n\n"

    return base


def _build_streaming_user_prompt(question: str, conversation_history: list[dict[str, str]] | None) -> str:
    prompt = question
    if conversation_history:
        history_text = "\n".join(
            f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content'][:200]}"
            for msg in conversation_history[-4:]
        )
        prompt = f"Previous conversation:\n{history_text}\n\nCurrent question: {prompt}"
    return prompt


def format_sse_event(event_type: str, data: dict[str, Any]) -> str:
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"
