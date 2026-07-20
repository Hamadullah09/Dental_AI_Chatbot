from __future__ import annotations

import time
from typing import Any

from app.agent.state import AgentState
from app.agent.nodes.planner import (
    detect_intent, can_answer_directly, generate_direct_answer,
    has_enough_evidence, search_more, respond_with_uncertainty,
    rewrite_query, build_context, validate_citations, format_response, handle_error,
)
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def retrieve_chunks(state: AgentState) -> AgentState:
    start = time.perf_counter()
    settings = get_settings()

    try:
        from app.services.rag import RAGService, merge_chunks, rerank_chunks, RetrievedChunk, SourceCitation
        rag = RAGService()
        query = state.rewritten_query or state.question
        top_k = state.top_k or settings.retrieval_top_k
        variants = state.query_variants or [query]

        rag_mode = settings.rag_mode

        if rag_mode == "multi_query" and len(variants) > 1:
            all_chunks = []
            seen_keys = set()
            for variant in variants[:settings.multi_query_max_variants]:
                variant_chunks = rag.retrieve(variant, top_k=top_k, filters=state.filters)
                for chunk in variant_chunks:
                    key = (chunk.citation.document_id, chunk.citation.page_number, chunk.citation.chunk_index)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        all_chunks.append(chunk)
            merged = merge_chunks(all_chunks)
            reranked = rerank_chunks(query, merged)
        elif rag_mode == "corrective" or rag_mode == "self_rag":
            initial = rag.retrieve(query, top_k=top_k, filters=state.filters)
            from app.services.rag import retrieval_confidence
            if retrieval_confidence(initial) >= settings.corrective_confidence_threshold:
                reranked = initial
            else:
                all_chunks = list(initial)
                seen_keys = set()
                for chunk in initial:
                    key = (chunk.citation.document_id, chunk.citation.page_number, chunk.citation.chunk_index)
                    seen_keys.add(key)
                for variant in variants[:settings.multi_query_max_variants]:
                    variant_chunks = rag.retrieve(variant, top_k=top_k, filters=state.filters)
                    for chunk in variant_chunks:
                        key = (chunk.citation.document_id, chunk.citation.page_number, chunk.citation.chunk_index)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            all_chunks.append(chunk)
                merged = merge_chunks(all_chunks)
                reranked = rerank_chunks(query, merged)
        elif rag_mode == "hyde":
            initial = rag.retrieve(query, top_k=top_k, filters=state.filters)
            from app.services.rag import retrieval_confidence
            if retrieval_confidence(initial) >= settings.hyde_confidence_threshold:
                reranked = initial
            else:
                hypothetical = rag.generate_hypothetical_passage(query)
                if hypothetical:
                    hyde_chunks = rag.retrieve(hypothetical, top_k=top_k, filters=state.filters)
                    all_chunks = initial + hyde_chunks
                    merged = merge_chunks(all_chunks)
                    reranked = rerank_chunks(query, merged)
                else:
                    reranked = initial
        else:
            reranked = rag.retrieve(query, top_k=top_k, filters=state.filters)

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
            for chunk in reranked
        ]

        duration_ms = (time.perf_counter() - start) * 1000
        state.add_trace("hybrid_retriever", "completed", f"{len(reranked)} chunks (mode={rag_mode})", duration_ms)

    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        state.error = str(exc)
        state.add_trace("hybrid_retriever", "error", str(exc), duration_ms)

    return state


def retrieve_visuals(state: AgentState) -> AgentState:
    start = time.perf_counter()
    settings = get_settings()

    if not settings.enable_multimodal_rag:
        state.add_trace("visual_retriever", "skipped", "Multimodal RAG disabled")
        return state

    if state.intent not in ("visual", "general") and not state.search_web:
        state.add_trace("visual_retriever", "skipped", f"Intent '{state.intent}' does not need visuals")
        return state

    try:
        from app.services.rag import RAGService, RetrievedChunk, RetrievedVisual
        from app.schemas import SourceCitation

        rag = RAGService()
        query = state.rewritten_query or state.question
        top_k = state.top_k or settings.retrieval_top_k

        retrieved_chunks_for_visuals = []
        for chunk_dict in state.retrieved_chunks[:top_k]:
            citation_data = chunk_dict.get("citation", {})
            retrieved_chunks_for_visuals.append(RetrievedChunk(
                text=chunk_dict.get("text", ""),
                citation=SourceCitation(
                    source_type=citation_data.get("source_type", "pdf"),
                    document_id=citation_data.get("document_id"),
                    document_name=citation_data.get("document_name", "Unknown"),
                    page_number=citation_data.get("page_number"),
                    chunk_index=citation_data.get("chunk_index"),
                    score=citation_data.get("score"),
                ),
                metadata={},
                vector_score=chunk_dict.get("vector_score", 0),
                keyword_score=chunk_dict.get("keyword_score", 0),
                rerank_score=chunk_dict.get("rerank_score", 0),
            ))

        visuals = rag.retrieve_visuals(query, chunks=retrieved_chunks_for_visuals, top_k=top_k, filters=state.filters)
        state.retrieved_visuals = [
            {
                "visual_id": v.citation.visual_id,
                "document_name": v.citation.document_name,
                "page_number": v.citation.page_number,
                "visual_type": v.citation.visual_type,
                "image_path": v.citation.image_path,
                "image_url": v.citation.image_url,
                "caption_text": v.citation.caption_text,
                "generated_description": v.citation.generated_description,
                "score": v.citation.score,
            }
            for v in visuals
        ]

        if visuals:
            visual_parts = []
            for v in visuals[:2]:
                desc = v.citation.generated_description or v.citation.caption_text or "No description"
                visual_parts.append(
                    f"[Visual: {v.citation.visual_type} from {v.citation.document_name}, "
                    f"page {v.citation.page_number}]\n{desc}"
                )
            state.visual_context = "\n\n".join(visual_parts)

        duration_ms = (time.perf_counter() - start) * 1000
        state.add_trace("visual_retriever", "completed", f"{len(visuals)} visuals", duration_ms)

    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        state.add_trace("visual_retriever", "error", str(exc), duration_ms)

    return state


def rerank_results(state: AgentState) -> AgentState:
    start = time.perf_counter()
    settings = get_settings()

    def _score_chunk(chunk: dict) -> float:
        vector = chunk.get("vector_score", 0)
        keyword = chunk.get("keyword_score", 0)
        rerank = chunk.get("rerank_score", 0)
        if settings.enable_bge_reranker and rerank > 0:
            return rerank
        return rerank * 0.4 + vector * 0.35 + keyword * 0.25

    state.reranked_chunks = sorted(state.retrieved_chunks, key=_score_chunk, reverse=True)

    min_relevance = settings.retrieval_min_relevance_score
    state.reranked_chunks = [
        c for c in state.reranked_chunks
        if c.get("rerank_score", 0) >= min_relevance * 0.5 or c.get("vector_score", 0) >= 0.3
    ]

    def _score_visual(visual: dict) -> float:
        return visual.get("score", 0) or 0

    state.reranked_visuals = sorted(state.retrieved_visuals, key=_score_visual, reverse=True)

    duration_ms = (time.perf_counter() - start) * 1000
    state.add_trace("reranker", "completed", f"{len(state.reranked_chunks)} chunks, {len(state.reranked_visuals)} visuals", duration_ms)
    return state


def generate_answer(state: AgentState) -> AgentState:
    start = time.perf_counter()

    try:
        from app.services.llm import LLMService
        llm = LLMService()

        system_prompt = _build_system_prompt(state)
        user_prompt = _build_user_prompt(state)

        answer = llm.generate(user_prompt, system_prompt=system_prompt)
        state.answer = answer
        state.answer_mode = "rag_grounded" if state.retrieved_chunks else "general_fallback"

        try:
            from app.services.rag import RAGService, contains_prescribing_language, needs_safety_note
            rag = RAGService()
            chunks_for_check = []
            for chunk_dict in state.reranked_chunks[:5]:
                from app.schemas import SourceCitation
                citation_data = chunk_dict.get("citation", {})
                chunks_for_check.append(type('RetrievedChunk', (), {
                    'text': chunk_dict.get("text", ""),
                    'citation': SourceCitation(
                        source_type=citation_data.get("source_type", "pdf"),
                        document_id=citation_data.get("document_id"),
                        document_name=citation_data.get("document_name", "Unknown"),
                        page_number=citation_data.get("page_number"),
                        chunk_index=citation_data.get("chunk_index"),
                        score=citation_data.get("score"),
                    ),
                    'metadata': {},
                    'vector_score': chunk_dict.get("vector_score", 0),
                    'keyword_score': chunk_dict.get("keyword_score", 0),
                    'rerank_score': chunk_dict.get("rerank_score", 0),
                })())

            check_result = rag.self_check_answer(state.question, state.answer, chunks_for_check)

            if not check_result.get("passed"):
                reasons = check_result.get("reasons", [])
                if "prescribing_language" in reasons:
                    state.answer = (
                        "I cannot provide specific medication prescriptions or dosages. "
                        "Please consult a licensed dental professional for prescription advice.\n\n"
                        + state.answer
                    )
                if "missing_safety_note" in reasons:
                    state.answer += (
                        "\n\n**Safety Note:** This is educational information only. "
                        "For symptoms, diagnosis, or treatment decisions, please consult a licensed dentist."
                    )
                if "ungrounded" in reasons and state.retrieved_chunks:
                    state.answer_mode = "partially_grounded"
                    state.add_trace("self_check", "flagged", f"Reasons: {reasons}")
        except Exception:
            pass

        for chunk in state.reranked_chunks[:5]:
            citation = chunk.get("citation", {})
            state.sources.append({
                "source_type": citation.get("source_type", "pdf"),
                "document_id": citation.get("document_id"),
                "document_name": citation.get("document_name", "Unknown"),
                "page_number": citation.get("page_number"),
                "chunk_index": citation.get("chunk_index"),
                "score": citation.get("score"),
            })

        for visual in state.reranked_visuals[:2]:
            state.visuals.append({
                "visual_id": visual.get("visual_id", ""),
                "document_id": visual.get("document_id"),
                "document_name": visual.get("document_name", "Unknown"),
                "page_number": visual.get("page_number"),
                "visual_type": visual.get("visual_type", "unknown"),
                "image_path": visual.get("image_path", ""),
                "image_url": visual.get("image_url", ""),
                "caption_text": visual.get("caption_text"),
                "generated_description": visual.get("generated_description"),
                "score": visual.get("score"),
            })

        duration_ms = (time.perf_counter() - start) * 1000
        state.add_trace("llm", "completed", f"Generated {len(answer)} chars", duration_ms)

    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        state.error = str(exc)
        state.add_trace("llm", "error", str(exc), duration_ms)

    return state


def _build_system_prompt(state: AgentState) -> str:
    settings = get_settings()
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
        "- Keep paragraphs short (2-3 sentences max)\n"
        "- Aim for 200-500 words for educational questions\n"
        "- For simple questions, keep answers brief\n"
        "- Always include [Source N] citations for factual claims\n"
        "- End with appropriate safety/consultation note\n\n"
    )

    if state.intent == "emergency":
        base += "IMPORTANT: This appears to be an emergency query. Emphasize seeking immediate professional dental care.\n\n"
    elif state.intent == "visual":
        base += "The user is asking about visual content. Reference any provided images, diagrams, or figures.\n\n"
    elif state.intent == "symptom":
        base += (
            "The user is asking about symptoms. Provide clear explanations of possible causes, "
            "when to see a dentist, and practical self-care tips. Always recommend professional evaluation.\n\n"
        )
    elif state.intent == "treatment":
        base += (
            "The user is asking about dental treatments. Explain procedures, expected outcomes, "
            "recovery information, and cost considerations where relevant.\n\n"
        )

    try:
        from app.services.rag import normalize_user_role, role_behavior_instruction
        role = normalize_user_role(state.user_role)
        base += role_behavior_instruction(state.user_role) + "\n\n"
    except Exception:
        pass

    if state.context_text:
        base += f"Context from dental knowledge base:\n{state.context_text}\n\n"

    return base


def _build_user_prompt(state: AgentState) -> str:
    prompt = state.question
    if state.conversation_history:
        history_text = "\n".join(
            f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content'][:200]}"
            for msg in state.conversation_history[-4:]
        )
        prompt = f"Previous conversation:\n{history_text}\n\nCurrent question: {prompt}"
    return prompt


def build_langgraph():
    from langgraph.graph import StateGraph, END

    workflow = StateGraph(AgentState)

    workflow.add_node("detect_intent", detect_intent)
    workflow.add_node("generate_direct_answer", generate_direct_answer)
    workflow.add_node("rewrite_query", rewrite_query)
    workflow.add_node("retrieve_chunks", retrieve_chunks)
    workflow.add_node("retrieve_visuals", retrieve_visuals)
    workflow.add_node("rerank_results", rerank_results)
    workflow.add_node("search_more", search_more)
    workflow.add_node("build_context", build_context)
    workflow.add_node("generate_answer", generate_answer)
    workflow.add_node("validate_citations", validate_citations)
    workflow.add_node("respond_with_uncertainty", respond_with_uncertainty)
    workflow.add_node("format_response", format_response)
    workflow.add_node("handle_error", handle_error)

    workflow.set_entry_point("detect_intent")

    workflow.add_conditional_edges(
        "detect_intent",
        can_answer_directly,
        {
            "yes": "generate_direct_answer",
            "no": "rewrite_query",
        },
    )

    workflow.add_edge("generate_direct_answer", "format_response")

    workflow.add_edge("rewrite_query", "retrieve_chunks")
    workflow.add_edge("retrieve_chunks", "retrieve_visuals")
    workflow.add_edge("retrieve_visuals", "rerank_results")

    workflow.add_conditional_edges(
        "rerank_results",
        has_enough_evidence,
        {
            "yes": "build_context",
            "no": "search_more",
        },
    )

    workflow.add_conditional_edges(
        "search_more",
        lambda state: "enough"
        if (state.retry_count <= state.max_retries and (state.retrieved_chunks or (state.intent == "visual" and state.retrieved_visuals)))
        else "uncertain",
        {
            "enough": "build_context",
            "uncertain": "respond_with_uncertainty",
        },
    )

    workflow.add_edge("build_context", "generate_answer")
    workflow.add_edge("generate_answer", "validate_citations")
    workflow.add_edge("validate_citations", "format_response")
    workflow.add_edge("respond_with_uncertainty", "format_response")
    workflow.add_edge("format_response", END)

    return workflow.compile()
