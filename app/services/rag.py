from dataclasses import dataclass
from functools import lru_cache
from collections import Counter
from types import SimpleNamespace
import json
import logging
import math
from pathlib import Path
import re

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sqlalchemy import or_

from app.core.database import SessionLocal
from app.core.config import get_settings
from app.models import Document, DocumentChunk, DocumentVisual
from app.schemas import SourceCitation, VisualCitation
from app.services.chunk_quality import assess_chunk_quality, is_form_or_survey_question
from app.services.embeddings import get_embedding_model
from app.services.llm import LLMGenerationError, LLMService
from app.services.vector_store import get_qdrant_client
from app.services.web_search import WebSearchResult, WebSearchService


logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    text: str
    citation: SourceCitation
    metadata: dict
    vector_score: float = 0.0
    keyword_score: float = 0.0
    rerank_score: float = 0.0


@dataclass
class RetrievedVisual:
    citation: VisualCitation
    metadata: dict
    vector_score: float = 0.0
    rerank_score: float = 0.0


@dataclass
class VisualObservation:
    visual: RetrievedVisual
    observation: str


@dataclass
class RAGAnswer:
    answer: str
    sources: list[SourceCitation]
    answer_mode: str
    visuals: list[VisualCitation] | None = None

    def __iter__(self):
        yield self.answer
        yield self.sources


class RAGService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedding_model = get_embedding_model()
        self.qdrant = get_qdrant_client()
        self.llm = LLMService()
        self.web_search = WebSearchService()

    def retrieve(self, question: str, top_k: int | None = None, filters: dict | None = None) -> list[RetrievedChunk]:
        retrieval_question = rewrite_query_for_retrieval(question) if self.settings.enable_query_rewriting else question
        vector = self.embedding_model.encode([retrieval_question])[0].tolist()
        requested_limit = top_k or self.settings.retrieval_top_k
        final_limit = min(5, max(3, requested_limit))
        candidate_limit = max(20, final_limit * 4)
        text_filters = {**(filters or {}), "payload_type": "text"}
        query_filter = build_qdrant_filter(text_filters)
        allow_noisy = bool((filters or {}).get("include_noisy")) or is_form_or_survey_question(question)

        vector_chunks = self.vector_search(vector, candidate_limit, query_filter)
        keyword_chunks = self.keyword_search(retrieval_question, candidate_limit, text_filters) if self.settings.enable_keyword_search else []
        merged = filter_chunks_for_question(question, merge_chunks(vector_chunks + keyword_chunks), allow_noisy=allow_noisy)
        if not merged and filters and not filters.get("document_id"):
            vector_chunks = self.vector_search(vector, candidate_limit, build_qdrant_filter({"payload_type": "text"}))
            keyword_chunks = self.keyword_search(retrieval_question, candidate_limit, {"payload_type": "text"}) if self.settings.enable_keyword_search else []
            merged = filter_chunks_for_question(question, merge_chunks(vector_chunks + keyword_chunks), allow_noisy=allow_noisy)
        reranked = rerank_chunks(question, merged)
        relevant = [
            chunk
            for chunk in reranked
            if is_relevant_chunk(question, chunk, self.settings.retrieval_min_relevance_score)
        ]
        if self.settings.enable_adjacent_chunk_expansion:
            relevant = self.expand_adjacent_chunks(question, relevant[:final_limit], filters or {})
        compressed = []
        for chunk in relevant[:final_limit]:
            compressed_text = compress_context(question, chunk.text)
            if not compressed_text:
                continue
            compressed.append(
                RetrievedChunk(
                    text=compressed_text,
                    citation=chunk.citation,
                    metadata=chunk.metadata,
                    vector_score=chunk.vector_score,
                    keyword_score=chunk.keyword_score,
                    rerank_score=chunk.rerank_score,
                )
            )
        return compressed

    def expand_adjacent_chunks(self, question: str, chunks: list[RetrievedChunk], filters: dict) -> list[RetrievedChunk]:
        if not chunks:
            return chunks
        expanded = list(chunks)
        selected_keys = {
            (chunk.citation.document_id or chunk.metadata.get("document_id"), chunk.citation.chunk_index)
            for chunk in chunks
        }
        for chunk in chunks[:3]:
            document_id = chunk.citation.document_id or chunk.metadata.get("document_id")
            chunk_index = chunk.citation.chunk_index
            if document_id is None or chunk_index is None:
                continue
            for neighbor_index in (int(chunk_index) - 1, int(chunk_index) + 1):
                neighbor = self.fetch_chunk_by_position(str(document_id), neighbor_index, filters)
                if neighbor and should_use_chunk(question, neighbor):
                    neighbor.metadata["adjacent_to_selected"] = True
                    expanded.append(neighbor)
        merged = merge_chunks(expanded)
        reranked = rerank_chunks(question, merged)
        return sorted(
            reranked,
            key=lambda chunk: (
                0
                if (chunk.citation.document_id or chunk.metadata.get("document_id"), chunk.citation.chunk_index) in selected_keys
                else 1,
                chunk.citation.document_id or "",
                chunk.citation.chunk_index if chunk.citation.chunk_index is not None else 10**9,
            ),
        )

    def fetch_chunk_by_position(self, document_id: str, chunk_index: int, filters: dict) -> RetrievedChunk | None:
        if chunk_index < 0:
            return None
        try:
            records, _ = self.qdrant.scroll(
                collection_name=self.settings.qdrant_collection,
                scroll_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(key="document_id", match=qmodels.MatchValue(value=document_id)),
                        qmodels.FieldCondition(key="chunk_index", match=qmodels.MatchValue(value=chunk_index)),
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
        except Exception:
            logger.exception("rag.adjacent_chunk.fetch_failed")
            return None
        if not records:
            return None
        payload = records[0].payload or {}
        if filters.get("review_status") and payload.get("review_status") != filters.get("review_status"):
            return None
        return self.payload_to_chunk(payload)

    def retrieve_for_mode(self, question: str, top_k: int | None = None, filters: dict | None = None) -> list[RetrievedChunk]:
        filters = filters or {}
        mode = normalize_rag_mode(self.settings.rag_mode)
        query_type = classify_query(question, filters)
        effective_mode = self.select_effective_mode(mode, query_type, question, filters)
        memory_context = self.build_memory_context(question, filters.get("conversation_history") or [])
        retrieval_question = f"{question}\n\nRelevant conversation memory:\n{memory_context}" if memory_context else question
        logger.info(
            "rag.retrieve.start",
            extra={"rag_mode": effective_mode, "query_type": query_type, "memory_used": bool(memory_context)},
        )

        if effective_mode == "simple":
            chunks = self.retrieve(retrieval_question, top_k=top_k, filters=filters)
        elif effective_mode == "memory":
            chunks = self.retrieve(retrieval_question, top_k=top_k, filters=filters)
        elif effective_mode == "multi_query":
            chunks = self.retrieve_multi_query(retrieval_question, question, top_k=top_k, filters=filters)
        elif effective_mode == "hyde":
            chunks = self.retrieve_hyde(retrieval_question, question, top_k=top_k, filters=filters)
        elif effective_mode in {"corrective", "self_rag"}:
            chunks = self.retrieve_corrective(retrieval_question, question, top_k=top_k, filters=filters)
        elif effective_mode == "agentic":
            logger.info("rag.agentic.deferred_to_corrective")
            chunks = self.retrieve_corrective(retrieval_question, question, top_k=top_k, filters=filters)
        else:
            chunks = self.retrieve(retrieval_question, top_k=top_k, filters=filters)

        logger.info(
            "rag.retrieve.complete",
            extra={"rag_mode": effective_mode, "query_type": query_type, "chunk_count": len(chunks)},
        )
        return chunks

    def select_effective_mode(self, mode: str, query_type: str, question: str, filters: dict) -> str:
        if mode == "adaptive":
            if query_type == "emergency_safety":
                return "simple"
            if filters.get("document_id"):
                return "corrective"
            if wants_roman_urdu(question):
                return "multi_query"
            if query_type in {"symptom_guidance", "treatment_question"}:
                return "corrective"
            return "multi_query"
        if self.settings.enable_memory and mode == "simple":
            return "memory"
        return mode

    def build_memory_context(self, question: str, history: list[dict]) -> str:
        if not self.settings.enable_memory or not history:
            return ""
        terms = question_keywords(question)
        original_terms = {
            token
            for token in re.findall(r"[a-zA-Z][a-zA-Z-]{2,}", question.lower())
            if token not in BM25_STOPWORDS
        }
        subject_terms = {
            normalize_lexical_token(token)
            for token in re.findall(r"[a-zA-Z][a-zA-Z-]{2,}", question.lower())
            if token not in BM25_STOPWORDS
        }
        expanded_terms = terms | subject_terms | original_terms
        if not terms and not is_followup_question(question):
            return ""
        kept: list[str] = []
        for item in history[-6:]:
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            content_tokens = set(bm25_tokens(content))
            content_l = content.lower()
            relevant = (
                bool(expanded_terms and (expanded_terms.intersection(content_tokens) or any(term in content_l for term in expanded_terms)))
                or is_followup_question(question)
            )
            if relevant:
                role = str(item.get("role") or "message")
                kept.append(f"{role}: {content[:320]}")
        return "\n".join(kept[-4:])

    def retrieve_multi_query(
        self,
        retrieval_question: str,
        original_question: str,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> list[RetrievedChunk]:
        variants = generate_query_variants(retrieval_question, max_variants=self.settings.multi_query_max_variants)
        variants = merge_query_variants(
            variants,
            self.generate_llm_query_variants(original_question, self.settings.multi_query_max_variants),
            self.settings.multi_query_max_variants,
        )
        logger.info("rag.multi_query.variants", extra={"variant_count": len(variants)})
        candidates: list[RetrievedChunk] = []
        for variant in variants:
            candidates.extend(self.retrieve(variant, top_k=max(5, top_k or self.settings.retrieval_top_k), filters=filters))
        merged = merge_chunks(candidates)
        reranked = rerank_chunks(original_question, merged)
        relevant = [
            chunk
            for chunk in reranked
            if is_relevant_chunk(original_question, chunk, self.settings.retrieval_min_relevance_score)
        ]
        return relevant[: min(5, max(3, top_k or self.settings.retrieval_top_k))]

    def retrieve_hyde(
        self,
        retrieval_question: str,
        original_question: str,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> list[RetrievedChunk]:
        initial = self.retrieve(retrieval_question, top_k=top_k, filters=filters)
        if not self.settings.enable_hyde or retrieval_confidence(initial) >= 1.35:
            return initial
        hypothetical = self.generate_hypothetical_passage(original_question)
        if not hypothetical:
            return initial
        logger.info("rag.hyde.used")
        hyde_chunks = self.retrieve(hypothetical, top_k=max(5, top_k or self.settings.retrieval_top_k), filters=filters)
        merged = merge_chunks(initial + hyde_chunks)
        reranked = rerank_chunks(original_question, merged)
        relevant = [
            chunk
            for chunk in reranked
            if is_relevant_chunk(original_question, chunk, self.settings.retrieval_min_relevance_score)
        ]
        return relevant[: min(5, max(3, top_k or self.settings.retrieval_top_k))]

    def retrieve_corrective(
        self,
        retrieval_question: str,
        original_question: str,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> list[RetrievedChunk]:
        initial = self.retrieve(retrieval_question, top_k=top_k, filters=filters)
        if retrieval_confidence(initial) >= 1.35:
            return initial
        logger.info("rag.corrective.retry")
        retried = self.retrieve_multi_query(retrieval_question, original_question, top_k=top_k, filters=filters)
        if retried or not self.settings.enable_hyde:
            return retried
        return self.retrieve_hyde(retrieval_question, original_question, top_k=top_k, filters=filters)

    def generate_hypothetical_passage(self, question: str) -> str:
        if not self.llm.is_configured:
            return ""
        prompt = (
            "Write a short ideal dental reference passage that would answer this search query. "
            "Do not answer the user directly. Do not include citations.\n\n"
            f"Query: {question}\n\n"
            "Hypothetical passage:"
        )
        try:
            return self.llm.generate(
                prompt,
                temperature=0.1,
                top_p=0.8,
                system_prompt="You create concise hypothetical retrieval passages for dental RAG search only.",
            )[:900]
        except LLMGenerationError:
            return ""

    def generate_llm_query_variants(self, question: str, max_variants: int) -> list[str]:
        llm = getattr(self, "llm", None)
        if not llm or not llm.is_configured or max_variants <= 1:
            return []
        prompt = (
            "Rewrite the user question into concise search queries for a dental reference corpus.\n"
            "Rules:\n"
            "- Return only a JSON array of strings.\n"
            "- Use English clinical wording for search, even if the user used Roman Urdu.\n"
            "- Do not answer the question.\n"
            "- Do not add citations.\n"
            f"- Return at most {max_variants} variants.\n\n"
            f"User question: {question}"
        )
        try:
            raw = llm.generate(
                prompt,
                temperature=0.1,
                top_p=0.8,
                system_prompt="You create retrieval search query rewrites only.",
            )
        except LLMGenerationError:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = re.findall(r'"([^"]{4,180})"', raw)
        if not isinstance(parsed, list):
            return []
        variants: list[str] = []
        for item in parsed:
            query = re.sub(r"\s+", " ", str(item)).strip()
            if query and len(query) <= 220:
                variants.append(query)
        return variants[:max_variants]

    def vector_search(
        self,
        vector: list[float],
        limit: int,
        query_filter: qmodels.Filter | None,
    ) -> list[RetrievedChunk]:
        hits = qdrant_vector_search_compatible(
            self.qdrant,
            collection_name=self.settings.qdrant_collection,
            vector=vector,
            limit=limit,
            query_filter=query_filter,
            settings=self.settings,
        )
        return [self.hit_to_chunk(hit, vector_score=float(hit.score or 0.0)) for hit in hits]

    def keyword_search(self, question: str, limit: int, filters: dict) -> list[RetrievedChunk]:
        query_tokens = bm25_tokens(question)
        if not query_tokens:
            return []

        rows = self.fetch_bm25_candidates(query_tokens, filters)
        if not rows:
            return []

        documents = []
        payloads = []
        for chunk, document in rows:
            payload = {
                "payload_type": "text",
                "chunk_id": chunk.qdrant_point_id,
                "qdrant_point_id": chunk.qdrant_point_id,
                "document_id": chunk.document_id,
                "document_name": document.canonical_title or document.title or document.original_filename,
                "book_title": document.canonical_title or document.title or document.original_filename,
                "title": document.title,
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "section_title": chunk.section_title,
                "chapter_title": chunk.chapter_title,
                "dental_specialty": chunk.dental_specialty or document.dental_specialty or document.specialty,
                "topic": chunk.topic or document.topic,
                "difficulty_level": chunk.difficulty_level or document.difficulty_level,
                "language": chunk.language or document.language,
                "trust_level": chunk.trust_level or getattr(document.trust_level, "value", document.trust_level),
                "review_status": chunk.review_status or getattr(document.review_status, "value", document.review_status),
                "document_type": getattr(document.document_type, "value", document.document_type),
                "year": document.publication_year,
                "text": chunk.text,
                "quality_score": chunk.quality_score,
                "is_noisy": chunk.is_noisy,
                "noise_reasons": chunk.noise_reasons,
            }
            payloads.append(payload)
            documents.append(bm25_tokens(chunk_search_text_from_payload(payload)))

        scores = bm25_scores(query_tokens, documents)
        chunks: list[RetrievedChunk] = []
        for payload, score in zip(payloads, scores):
            if score <= 0:
                continue
            retrieved = self.payload_to_chunk(payload, keyword_score=score)
            if should_use_chunk(question, retrieved, allow_noisy=bool(filters.get("include_noisy"))):
                chunks.append(retrieved)
        return sorted(chunks, key=lambda chunk: chunk.keyword_score, reverse=True)[:limit]

    def fetch_bm25_candidates(self, query_tokens: list[str], filters: dict):
        db = SessionLocal()
        try:
            query = (
                db.query(DocumentChunk, Document)
                .join(Document, DocumentChunk.document_id == Document.id)
                .filter(DocumentChunk.text.isnot(None))
            )
            if not filters.get("include_noisy"):
                query = query.filter(DocumentChunk.is_noisy.is_(False)).filter(DocumentChunk.quality_score >= 0.55)
            if filters.get("document_id"):
                query = query.filter(DocumentChunk.document_id == str(filters["document_id"]))
            if filters.get("review_status"):
                query = query.filter(DocumentChunk.review_status == str(filters["review_status"]))
            if filters.get("min_year"):
                query = query.filter(Document.publication_year >= int(filters["min_year"]))
            if filters.get("language"):
                query = query.filter(DocumentChunk.language == str(filters["language"]))
            if filters.get("dental_specialty"):
                query = query.filter(DocumentChunk.dental_specialty == str(filters["dental_specialty"]))
            if filters.get("trust_levels"):
                query = query.filter(DocumentChunk.trust_level.in_([str(value) for value in list_filter_values(filters["trust_levels"])]))
            if filters.get("document_types"):
                query = query.filter(Document.document_type.in_(list_filter_values(filters["document_types"])))

            searchable_terms = [term for term in query_tokens if len(term) >= 3][:10]
            if searchable_terms:
                conditions = []
                for term in searchable_terms:
                    pattern = f"%{term}%"
                    conditions.extend(
                        [
                            DocumentChunk.text.ilike(pattern),
                            DocumentChunk.section_title.ilike(pattern),
                            DocumentChunk.chapter_title.ilike(pattern),
                            DocumentChunk.topic.ilike(pattern),
                            Document.canonical_title.ilike(pattern),
                            Document.title.ilike(pattern),
                            Document.topic.ilike(pattern),
                        ]
                    )
                query = query.filter(or_(*conditions))

            return (
                query.order_by(DocumentChunk.quality_score.desc(), DocumentChunk.chunk_index.asc())
                .limit(self.settings.keyword_search_scan_limit)
                .all()
            )
        finally:
            db.close()

    def hit_to_chunk(self, hit, vector_score: float = 0.0) -> RetrievedChunk:
        return self.payload_to_chunk(hit.payload or {}, vector_score=vector_score)

    def payload_to_chunk(
        self,
        payload: dict,
        vector_score: float = 0.0,
        keyword_score: float = 0.0,
    ) -> RetrievedChunk:
        text = str(payload.get("text") or "").strip()
        quality = assess_chunk_quality(text)
        payload = {
            **payload,
            "chunk_id": payload.get("chunk_id") or payload.get("qdrant_point_id"),
            "quality_score": float(payload.get("quality_score", quality.quality_score) or 0.0),
            "is_noisy": bool(payload.get("is_noisy", quality.is_noisy)),
            "noise_reasons": payload.get("noise_reasons") or quality.noise_reasons,
        }
        return RetrievedChunk(
            text=text,
            citation=SourceCitation(
                document_id=payload.get("document_id"),
                document_name=str(
                    payload.get("book_title")
                    or payload.get("title")
                    or payload.get("document_name")
                    or payload.get("source")
                    or "Unknown document"
                ),
                page_number=payload.get("page_number"),
                chunk_index=payload.get("chunk_index"),
                score=vector_score or keyword_score or None,
            ),
            metadata=payload,
            vector_score=vector_score,
            keyword_score=keyword_score,
        )

    def retrieve_visuals(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        top_k: int = 4,
        filters: dict | None = None,
    ) -> list[RetrievedVisual]:
        if not self.settings.enable_multimodal_rag:
            return []
        if wants_no_visual_answer(question):
            return []
        vector = self.embedding_model.encode([rewrite_query_for_retrieval(question)])[0].tolist()
        visual_filter = build_qdrant_filter({**(filters or {}), "payload_type": "visual"})
        try:
            hits = qdrant_vector_search_compatible(
                self.qdrant,
                collection_name=self.settings.qdrant_collection,
                vector=vector,
                limit=max(12, top_k * 4),
                query_filter=visual_filter,
                settings=self.settings,
            )
        except Exception:
            logger.exception("rag.visual_retrieve.failed")
            hits = []
        visuals = [self.payload_to_visual(hit.payload or {}, vector_score=float(hit.score or 0.0)) for hit in hits]
        if self.settings.enable_keyword_search:
            visuals.extend(self.visual_keyword_search(question, limit=max(12, top_k * 4), filters=filters or {}))
        visuals.extend(self.retrieve_chunk_linked_visuals(chunks, top_k=max(8, top_k * 3)))
        visuals = merge_visuals(visuals)
        reranked = rerank_visuals(question, visuals, chunks)
        threshold = self.settings.visual_min_relevance_score
        if wants_visual_answer(question):
            threshold *= 0.75
        return [visual for visual in reranked if visual.rerank_score >= threshold][:top_k]

    def visual_keyword_search(self, question: str, limit: int, filters: dict) -> list[RetrievedVisual]:
        query_tokens = bm25_tokens(question)
        if not query_tokens:
            return []

        rows = self.fetch_visual_bm25_candidates(query_tokens, filters)
        if not rows:
            return []

        documents = []
        payloads = []
        for visual in rows:
            payload = self.visual_payload_from_row(visual)
            payloads.append(payload)
            documents.append(bm25_tokens(visual_search_text_from_payload(payload)))

        scores = bm25_scores(query_tokens, documents)
        visuals: list[RetrievedVisual] = []
        for payload, score in zip(payloads, scores):
            if score <= 0:
                continue
            payload["keyword_score"] = score
            visuals.append(self.payload_to_visual(payload, vector_score=score))
        return sorted(visuals, key=lambda visual: visual.vector_score, reverse=True)[:limit]

    def fetch_visual_bm25_candidates(self, query_tokens: list[str], filters: dict):
        db = SessionLocal()
        try:
            query = db.query(DocumentVisual).filter(DocumentVisual.quality_score >= 0.45)
            if filters.get("document_id"):
                query = query.filter(DocumentVisual.document_id == str(filters["document_id"]))
            if filters.get("review_status"):
                query = query.filter(DocumentVisual.review_status == str(filters["review_status"]))

            searchable_terms = [term for term in query_tokens if len(term) >= 3][:10]
            if searchable_terms:
                conditions = []
                for term in searchable_terms:
                    pattern = f"%{term}%"
                    conditions.extend(
                        [
                            DocumentVisual.caption_text.ilike(pattern),
                            DocumentVisual.nearby_text.ilike(pattern),
                            DocumentVisual.generated_description.ilike(pattern),
                            DocumentVisual.document_name.ilike(pattern),
                            DocumentVisual.visual_type.ilike(pattern),
                        ]
                    )
                query = query.filter(or_(*conditions))

            return (
                query.order_by(DocumentVisual.quality_score.desc(), DocumentVisual.page_number.asc())
                .limit(self.settings.keyword_search_scan_limit)
                .all()
            )
        finally:
            db.close()

    def retrieve_chunk_linked_visuals(self, chunks: list[RetrievedChunk], top_k: int = 8) -> list[RetrievedVisual]:
        if not chunks:
            return []
        chunk_pages = {
            (chunk.citation.document_id, chunk.citation.page_number)
            for chunk in chunks
            if chunk.citation.document_id and chunk.citation.page_number
        }
        related_chunk_ids = {
            str(chunk.metadata.get("chunk_id") or chunk.metadata.get("qdrant_point_id"))
            for chunk in chunks
            if chunk.metadata.get("chunk_id") or chunk.metadata.get("qdrant_point_id")
        }
        document_ids = sorted({document_id for document_id, _ in chunk_pages if document_id})
        if not document_ids:
            return []

        db = SessionLocal()
        try:
            rows = (
                db.query(DocumentVisual)
                .filter(DocumentVisual.document_id.in_(document_ids))
                .order_by(DocumentVisual.quality_score.desc())
                .limit(250)
                .all()
            )
        finally:
            db.close()

        visuals: list[RetrievedVisual] = []
        for row in rows:
            row_related_ids = parse_related_chunk_ids(row.related_chunk_ids)
            is_same_page = (row.document_id, row.page_number) in chunk_pages
            is_related_chunk = bool(row_related_ids and row_related_ids.intersection(related_chunk_ids))
            if not is_same_page and not is_related_chunk:
                continue
            visual = self.visual_row_to_retrieved(row, row_related_ids)
            visual.vector_score = 0.12 if is_same_page else 0.0
            visuals.append(visual)
            if len(visuals) >= top_k:
                break
        return visuals

    def visual_row_to_retrieved(self, row: DocumentVisual, related_chunk_ids: set[str]) -> RetrievedVisual:
        payload = self.visual_payload_from_row(row)
        payload["related_chunk_ids"] = sorted(related_chunk_ids)
        return self.payload_to_visual(payload)

    def visual_payload_from_row(self, row: DocumentVisual) -> dict:
        return {
            "payload_type": "visual",
            "visual_id": row.visual_id,
            "qdrant_point_id": row.qdrant_point_id,
            "document_id": row.document_id,
            "document_name": row.document_name,
            "page_number": row.page_number,
            "visual_type": row.visual_type,
            "image_path": row.image_path,
            "image_url": image_url_for_visual_path(row.image_path),
            "caption_text": row.caption_text,
            "nearby_text": row.nearby_text,
            "generated_description": row.generated_description,
            "related_chunk_ids": parse_related_chunk_ids(row.related_chunk_ids),
            "quality_score": row.quality_score,
            "review_status": row.review_status,
            "content_hash": row.content_hash,
        }

    def payload_to_visual(self, payload: dict, vector_score: float = 0.0) -> RetrievedVisual:
        image_path = str(payload.get("image_path") or "")
        image_url = str(payload.get("image_url") or image_url_for_visual_path(image_path))
        citation = VisualCitation(
            visual_id=str(payload.get("visual_id") or payload.get("qdrant_point_id") or ""),
            document_id=payload.get("document_id"),
            document_name=str(payload.get("document_name") or payload.get("book_title") or "Unknown document"),
            page_number=payload.get("page_number"),
            visual_type=str(payload.get("visual_type") or "unknown"),
            image_path=image_path,
            image_url=image_url,
            caption_text=payload.get("caption_text"),
            generated_description=payload.get("generated_description"),
            score=vector_score or None,
        )
        return RetrievedVisual(citation=citation, metadata=payload, vector_score=vector_score)

    def build_prompt(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        visual_observations: list[VisualObservation] | None = None,
        user_role: str | None = None,
    ) -> str:
        normalized_role = normalize_user_role(user_role)
        context = "\n\n".join(
            f"[{idx}] {chunk.citation.document_name}, page {chunk.citation.page_number}, "
            f"chunk {chunk.citation.chunk_index}\n{chunk.text}"
            for idx, chunk in enumerate(chunks, start=1)
        )
        visual_context = "\n\n".join(
            f"[Visual {idx}] {item.visual.citation.document_name}, page {item.visual.citation.page_number}, "
            f"type {item.visual.citation.visual_type}\nObservation: {item.observation}"
            for idx, item in enumerate(visual_observations or [], start=1)
        )
        language_instruction = answer_language_instruction(question)
        return (
            f"Authenticated user role:\n{normalized_role}\n\n"
            f"User question:\n{question}\n\n"
            f"Retrieved dental library context:\n{context}\n\n"
            f"Relevant visual observations:\n{visual_context or 'No relevant visual observations.'}\n\n"
            f"Language instruction: {language_instruction}\n\n"
            "Answer the question using the system instructions and the authenticated user role.\n\n"
            "Use visual observations only as supporting evidence when they directly answer the question. "
            "If there are no relevant visual observations, answer from text context only. "
            "Never invent visual findings. Never diagnose from an image. "
            "Do not repeat the user's question. "
            "Do not copy raw chunk sentences as the answer. "
            "Synthesize the answer in your own words. Prefer retrieved dental library evidence when it is useful, "
            "and use reliable general dental knowledge only to make the explanation complete and understandable. "
            "Do not tell the user which parts came from retrieval unless they ask for sources. "
            "If the question asks what type of evidence is present, classify the evidence type directly "
            "(for example: clinical observational evidence, randomized trial evidence, systematic review evidence, "
            "expert opinion, guideline recommendation, table/statistical evidence, or uncertain/limited evidence). "
            "Write a complete final answer with real content. "
            "Start with a short, direct answer in 1 to 3 sentences. "
            "Use meaningful Markdown headings that match the question instead of rigid labels such as Direct Answer. "
            "Use bold text for important dental terms, symptoms, treatments, and warnings. "
            "Use short paragraphs and bullet points where they improve readability. "
            "For educational condition questions, include the relevant definition, causes, progression, symptoms, prevention, and when dental care is needed. "
            "Aim for 250 to 500 words for detailed educational questions, and shorter answers for simple questions. "
            "Only include safety guidance when it adds practical value for symptoms, diagnosis, medication, or treatment decisions. "
            "Never output placeholders such as [answer], [2-4 bullet points], [safety note], or template instructions."
        )

    def generate_answer(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        visual_observations: list[VisualObservation] | None = None,
        user_role: str | None = None,
    ) -> str:
        if not chunks:
            return (
                "I do not have enough relevant evidence in the uploaded documents to answer that reliably. "
                "For symptoms or treatment decisions, please consult a licensed dental professional."
            )

        prompt = self.build_prompt(question, chunks, visual_observations, user_role=user_role)
        llm = getattr(self, "llm", None)
        if not llm or not llm.is_configured:
            return service_unavailable_answer(question)

        try:
            answer = llm.generate(
                prompt,
                temperature=0.1,
                top_p=0.8,
                system_prompt=rag_system_prompt(question, user_role=user_role),
            )
            return self.ensure_language_style(question, answer)
        except LLMGenerationError:
            logger.exception("rag.text_model.failed")
            return service_unavailable_answer(question)

    def ensure_language_style(self, question: str, answer: str) -> str:
        cleaned = strip_model_sources(answer)
        if not wants_roman_urdu(question) or not self.llm.is_configured:
            return repair_patient_facing_answer(question, cleaned)
        prompt = (
            "Rewrite the following answer into Roman Urdu only.\n\n"
            "Rules:\n"
            "- Use English letters only.\n"
            "- Do not use Urdu script, Arabic script, Devanagari, or Persian script.\n"
            "- Do not leave the answer in English.\n"
            "- Use natural Pakistani Roman Urdu wording.\n"
            "- Keep dental terms when needed, but explain them in Roman Urdu.\n"
            "- Preserve the meaning.\n"
            "- Do not add sources or citations.\n"
            "- Do not show reasoning.\n\n"
            f"Answer:\n{cleaned}\n\n"
            "Roman Urdu:"
        )
        try:
            rewritten = strip_model_sources(
                self.llm.generate(
                    prompt,
                    temperature=0.1,
                    system_prompt=(
                        "You transliterate and rewrite dental explanations into Roman Urdu. "
                        "Use English letters only. Never use Urdu or Arabic script."
                    ),
                )
            )
            return repair_patient_facing_answer(question, rewritten)
        except LLMGenerationError:
            return repair_patient_facing_answer(question, cleaned)

    def generate_hybrid_answer(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        web_results: list[WebSearchResult],
        user_role: str | None = None,
    ) -> str:
        if not web_results:
            return (
                "I could not find enough trusted web evidence for that question right now. "
                "Please try again later or ask using the uploaded PDF sources."
            )
        if not self.llm.is_configured:
            return web_results_fallback_answer(web_results)

        pdf_context = "\n\n".join(
            f"[PDF {idx}] {chunk.citation.document_name}, page {chunk.citation.page_number}\n{chunk.text}"
            for idx, chunk in enumerate(chunks[:3], start=1)
        )
        web_context = "\n\n".join(
            f"[WEB {idx}] {result.title}\nURL: {result.url}\n{result.content}"
            for idx, result in enumerate(web_results, start=1)
        )
        prompt = (
            f"Authenticated user role:\n{normalize_user_role(user_role)}\n\n"
            f"PDF evidence:\n{pdf_context or 'No strong PDF evidence.'}\n\n"
            f"Trusted web evidence:\n{web_context}\n\n"
            f"User question:\n{question}\n\n"
            "Task:\n"
            "Answer using only the PDF and trusted web evidence.\n\n"
            "Rules:\n"
            "1. Follow the user's requested language exactly.\n"
            "2. If Roman Urdu is requested, use English letters only and do not use Urdu/Arabic script.\n"
            "3. Do not write source names, page numbers, citations, or a Sources section. The backend shows sources separately.\n"
            "4. Do not dump raw evidence.\n"
            "5. If evidence is insufficient, say so.\n"
            "6. Do not diagnose or prescribe.\n"
            "7. Do not show reasoning.\n\n"
            "Answer:"
        )
        try:
            answer = self.llm.generate(
                prompt,
                temperature=0.2,
                system_prompt=rag_system_prompt(question, user_role=user_role),
            )
            return self.ensure_language_style(question, answer)
        except LLMGenerationError:
            return web_results_fallback_answer(web_results)

    def answer(
        self,
        question: str,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> RAGAnswer:
        filters = filters or {}
        user_role = normalize_user_role(filters.get("user_role"))
        try:
            chunks = self.retrieve_for_mode(question, top_k=top_k, filters=filters)
        except Exception:
            logger.exception("rag.retrieve.failed")
            chunks = []
        wants_web = bool(filters.get("search_web"))

        if wants_web:
            try:
                web_results = self.web_search.search(question) if self.web_search.is_configured else []
            except Exception as exc:
                return RAGAnswer(
                    f"Web search could not run right now: {exc} "
                    "I can still answer from uploaded PDFs when relevant evidence is available.",
                    [],
                    "insufficient_evidence",
                )
            if web_results:
                answer = self.generate_hybrid_answer(question, chunks, web_results, user_role=user_role)
                citations = []
                if wants_sources(question):
                    citations = dedupe_citations([chunk.citation for chunk in chunks[:3]])
                    citations.extend(result.to_citation() for result in web_results)
                return RAGAnswer(answer, citations, "web_augmented")
            if wants_web and not self.web_search.is_configured:
                return RAGAnswer(
                    "Web search is not configured yet. Add a Google, Tavily, or Brave Search API key to enable trusted online browsing. "
                    "I can still answer from uploaded PDFs when relevant evidence is available.",
                    [],
                    "insufficient_evidence",
                )

        if not chunks:
            fallback_answer = self.generate_general_fallback_answer(question, user_role=user_role)
            if fallback_answer:
                return RAGAnswer(fallback_answer, [], "general_fallback")
            return RAGAnswer(
                "I do not have enough relevant evidence in the uploaded documents.",
                [],
                "insufficient_evidence",
            )

        retrieved_visuals = self.retrieve_visuals(question, chunks, filters=filters)
        visual_observations = self.analyze_retrieved_visuals(question, retrieved_visuals)
        usable_visuals = [item.visual for item in visual_observations if item.observation not in {"VISUAL_NOT_RELEVANT", "VISUAL_UNREADABLE"}]

        local_answer = self.generate_answer(question, chunks, visual_observations, user_role=user_role)
        if is_service_unavailable_answer(local_answer):
            return RAGAnswer(local_answer, [], "service_unavailable", [])
        if is_insufficient_answer(local_answer):
            return RAGAnswer(
                "I do not have enough relevant evidence in the uploaded documents.",
                [],
                "insufficient_evidence",
            )
        answer = local_answer
        citations = dedupe_citations([chunk.citation for chunk in chunks]) if wants_sources(question) else []
        visuals = [visual.citation for visual in usable_visuals]
        if self.settings.enable_self_check or normalize_rag_mode(self.settings.rag_mode) == "self_rag":
            check = self.self_check_answer(question, answer, chunks)
            logger.info("rag.self_check", extra=check)
            if not check["passed"]:
                if "ungrounded" in check["reasons"]:
                    return RAGAnswer(
                        "I do not have enough relevant evidence in the uploaded documents.",
                        [],
                        "insufficient_evidence",
                        [],
                    )
                answer = enforce_safety_note(answer, question)
        return RAGAnswer(answer, citations, "rag_grounded", visuals)

    def analyze_retrieved_visuals(
        self,
        question: str,
        visuals: list[RetrievedVisual],
    ) -> list[VisualObservation]:
        if not visuals:
            return []
        should_use_vision = wants_visual_answer(question) or any(
            visual.rerank_score >= self.settings.visual_min_relevance_score for visual in visuals
        )
        if not should_use_vision:
            return []
        observations: list[VisualObservation] = []
        for visual in visuals[:2]:
            try:
                observation = self.analyze_visual(question, visual)
            except LLMGenerationError:
                logger.exception(
                    "rag.vision_model.failed",
                    extra={"visual_id": visual.citation.visual_id, "visual_type": visual.citation.visual_type},
                )
                continue
            if not observation:
                continue
            observations.append(VisualObservation(visual=visual, observation=observation))
        return observations

    def analyze_visual(self, question: str, visual: RetrievedVisual) -> str:
        llm = getattr(self, "llm", None)
        if not llm or not llm.is_configured:
            raise LLMGenerationError("LLM is not configured for visual analysis.")
        prompt = (
            f"User question:\n{question}\n\n"
            "Retrieved visual metadata:\n"
            f"- Document: {visual.citation.document_name}\n"
            f"- Page: {visual.citation.page_number}\n"
            f"- Type: {visual.citation.visual_type}\n"
            f"- Caption: {visual.citation.caption_text or 'None'}\n"
            f"- Existing description: {visual.citation.generated_description or 'None'}\n\n"
            "Task:\n"
            "Return concise visual observations only if this image directly helps answer the question.\n"
            "If the visual does not match the question, return exactly: VISUAL_NOT_RELEVANT\n"
            "If the image is too blurry, cropped, unreadable, or low quality, return exactly: VISUAL_UNREADABLE\n"
            "Never diagnose from the image. Never prescribe medication. Do not invent findings.\n"
            "If the user asks in Roman Urdu, use English letters only.\n"
            "Keep the response under 80 words."
        )
        system_prompt = (
            "You are a dental visual-analysis assistant. "
            "You only describe visible, relevant figure/table/chart/diagram/image content. "
            "Do not diagnose, prescribe, or infer unsupported findings. "
            "Return VISUAL_NOT_RELEVANT or VISUAL_UNREADABLE when required."
        )
        observation = llm.analyze_image(
            visual.citation.image_path,
            prompt,
            system_prompt=system_prompt,
            temperature=0.0,
        )
        cleaned = strip_model_sources(observation).strip()
        if "VISUAL_NOT_RELEVANT" in cleaned.upper():
            return "VISUAL_NOT_RELEVANT"
        if "VISUAL_UNREADABLE" in cleaned.upper():
            return "VISUAL_UNREADABLE"
        return cleaned[:700]

    def generate_general_fallback_answer(self, question: str, user_role: str | None = None) -> str | None:
        if not self.settings.allow_general_fallback:
            return None
        if not self.llm.is_configured:
            return service_unavailable_answer(question)
        prompt = (
            f"Authenticated user role:\n{normalize_user_role(user_role)}\n\n"
            f"User question:\n{question}\n\n"
            "Retrieved dental library context:\nNo useful retrieved context was available for this question.\n\n"
            "Answer using reliable general dental education. Do not mention retrieval, database, chunks, fallback, or uploaded documents.\n\n"
            "Write a complete final answer with real content. "
            "Start with a short, direct answer in 1 to 3 sentences. "
            "Use meaningful Markdown headings that match the question instead of rigid labels such as Direct Answer. "
            "Use bold text for important dental terms, symptoms, treatments, and warnings. "
            "Use short paragraphs and bullet points where they improve readability. "
            "For educational condition questions, include the relevant definition, causes, progression, symptoms, prevention, and when dental care is needed. "
            "Never output placeholders such as [answer], [2-4 bullet points], [safety note], or template instructions."
        )
        try:
            answer = self.llm.generate(
                prompt,
                temperature=0.1,
                top_p=0.8,
                system_prompt=general_fallback_system_prompt(question, user_role=user_role),
            )
            return self.ensure_language_style(question, answer)
        except LLMGenerationError:
            logger.exception("rag.general_fallback_model.failed")
            return service_unavailable_answer(question)

    def self_check_answer(self, question: str, answer: str, chunks: list[RetrievedChunk]) -> dict:
        reasons: list[str] = []
        context = " ".join(chunk.text for chunk in chunks)
        answer_terms = question_keywords(answer)
        context_l = context.lower()
        if chunks and answer_terms:
            grounded_terms = [term for term in answer_terms if term in context_l or term in question.lower()]
            if len(grounded_terms) / max(len(answer_terms), 1) < 0.25:
                reasons.append("ungrounded")
        if contains_prescribing_language(answer):
            reasons.append("prescribing_language")
        if needs_safety_note(question) and "consult" not in answer.lower() and "dentist" not in answer.lower():
            reasons.append("missing_safety_note")
        if wants_roman_urdu(question) and contains_non_roman_script(answer):
            reasons.append("language_mismatch")
        return {"passed": not reasons, "reasons": reasons}

    def generate_extract_answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        if is_translation_or_language_request(question):
            return generate_language_fallback_answer(question, chunks)

        context = " ".join(chunk.text for chunk in chunks)
        sentences = split_sentences(context)
        definition_question = is_definition_question(question)

        code_answer = extract_code_answer(question, context)
        if code_answer:
            return (
                f"{code_answer}\n\n"
                "For clinical or academic use, verify the source material before relying on it."
            )

        keywords = question_keywords(question)
        ranked = rank_sentences(sentences, keywords)
        selected = ranked[:4] if ranked else sentences[:3]
        selected = [sentence for sentence in selected if sentence.strip()]
        if definition_question:
            selected = [sentence for sentence in selected if has_definition_signal(sentence)]
        if not selected:
            return (
                "I do not have enough relevant evidence in the uploaded documents to answer that directly. "
                "For symptoms or treatment decisions, please consult a licensed dental professional."
            )

        answer = " ".join(selected)
        if len(answer) > 1200:
            answer = answer[:1200].rsplit(" ", 1)[0] + "."
        return (
            f"{answer}\n\n"
            "For personal symptoms or treatment decisions, consult a licensed dental professional."
        )


def split_sentences(text: str) -> list[str]:
    cleaned = clean_context_text(text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", cleaned)
    return [part.strip() for part in parts if len(part.strip()) > 25 and not is_noisy_sentence(part)]


def qdrant_vector_search_compatible(
    qdrant: QdrantClient,
    *,
    collection_name: str,
    vector: list[float],
    limit: int,
    query_filter: qmodels.Filter | None,
    settings,
) -> list:
    if settings.qdrant_url:
        return legacy_qdrant_search(
            collection_name=collection_name,
            vector=vector,
            limit=limit,
            query_filter=query_filter,
            settings=settings,
        )
    try:
        if hasattr(qdrant, "search"):
            return qdrant.search(
                collection_name=collection_name,
                query_vector=vector,
                limit=limit,
                query_filter=query_filter,
            )
        query_result = qdrant.query_points(
            collection_name=collection_name,
            query=vector,
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
        )
        return list(query_result.points)
    except Exception as exc:
        if not should_use_legacy_qdrant_search(exc, settings):
            raise
        return legacy_qdrant_search(
            collection_name=collection_name,
            vector=vector,
            limit=limit,
            query_filter=query_filter,
            settings=settings,
        )


def should_use_legacy_qdrant_search(exc: Exception, settings) -> bool:
    message = str(exc).lower()
    return bool(settings.qdrant_url) and (
        "404" in message
        or "not found" in message
        or "query_points" in message
        or "unexpected response" in message
    )


def legacy_qdrant_search(
    *,
    collection_name: str,
    vector: list[float],
    limit: int,
    query_filter: qmodels.Filter | None,
    settings,
) -> list:
    base_url = str(settings.qdrant_url).rstrip("/")
    payload: dict = {
        "vector": vector,
        "limit": limit,
        "with_payload": True,
        "with_vector": False,
    }
    if query_filter is not None:
        payload["filter"] = qdrant_model_dump(query_filter)
    headers = {}
    if settings.qdrant_api_key:
        headers["api-key"] = settings.qdrant_api_key
    response = httpx.post(
        f"{base_url}/collections/{collection_name}/points/search",
        json=payload,
        headers=headers,
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return [
        SimpleNamespace(
            id=item.get("id"),
            score=float(item.get("score") or 0.0),
            payload=item.get("payload") or {},
        )
        for item in data.get("result", [])
    ]


def qdrant_model_dump(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=True, mode="json")
    if hasattr(model, "dict"):
        return model.dict(exclude_none=True)
    return dict(model)


def is_definition_question(question: str) -> bool:
    normalized = re.sub(r"[^a-zA-Z0-9\s?]", " ", question.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    definition_patterns = ("what is", "what are", "define", "meaning of", "what do you mean by")
    return any(normalized.startswith(pattern) for pattern in definition_patterns)


def is_evidence_type_question(question: str) -> bool:
    normalized = re.sub(r"[^a-zA-Z0-9\s?]", " ", question.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return "type of evidence" in normalized or (
        "evidence" in normalized and any(term in normalized for term in ["what type", "kind of", "present in the chunk"])
    )


def generate_evidence_type_answer(chunks: list[RetrievedChunk]) -> str:
    evidence_text = " ".join(chunk.text for chunk in chunks[:2]).lower()
    if not evidence_text.strip():
        return "I do not have enough relevant evidence in the uploaded documents."

    evidence_type = "limited clinical evidence"
    explanation = "The retrieved chunk discusses the strength or uncertainty of evidence rather than giving a direct treatment instruction."
    if any(term in evidence_text for term in ["systematic review", "meta-analysis", "meta analysis"]):
        evidence_type = "systematic review evidence"
        explanation = "The chunk appears to summarize evidence across multiple studies."
    elif any(term in evidence_text for term in ["randomized", "randomised", "controlled trial", "rct"]):
        evidence_type = "randomized controlled trial evidence"
        explanation = "The chunk refers to controlled clinical research comparing interventions or groups."
    elif any(term in evidence_text for term in ["cohort", "case-control", "case control", "follow-up", "follow up", "more likely", "risk", "association"]):
        evidence_type = "observational or associational clinical evidence"
        explanation = "The chunk links orthodontic treatment/history with later outcomes, but it does not prove a direct cause-and-effect relationship."
    elif any(term in evidence_text for term in ["case report", "case series"]):
        evidence_type = "case-based clinical evidence"
        explanation = "The chunk appears to describe individual or grouped clinical cases rather than broad comparative evidence."
    elif any(term in evidence_text for term in ["guideline", "recommendation", "consensus"]):
        evidence_type = "guideline or expert recommendation evidence"
        explanation = "The chunk presents a recommendation or consensus-style statement rather than primary study data."
    elif any(term in evidence_text for term in ["survey", "questionnaire"]):
        evidence_type = "survey/questionnaire evidence"
        explanation = "The chunk appears to rely on reported responses rather than direct clinical measurement."
    elif any(term in evidence_text for term in ["table", "statistical", "p value", "confidence interval", "%"]):
        evidence_type = "statistical or tabulated evidence"
        explanation = "The chunk appears to present measured or summarized data."
    elif any(term in evidence_text for term in ["less clear", "unclear", "limited evidence", "insufficient evidence"]):
        evidence_type = "limited or uncertain evidence"
        explanation = "The chunk explicitly suggests the evidence is not strong or clear enough for a firm conclusion."

    return (
        f"## Evidence Type\n\nThe retrieved chunk contains **{evidence_type}**.\n\n"
        f"## Why this fits\n\n{explanation}"
    )


def has_definition_signal(sentence: str) -> bool:
    normalized = re.sub(r"\s+", " ", sentence.lower()).strip()
    definition_signals = [
        " is ",
        " are ",
        " means ",
        " mean ",
        " refers to ",
        " defined as ",
        " definition ",
        " consists of ",
        " includes ",
    ]
    return any(signal in f" {normalized} " for signal in definition_signals)


def is_insufficient_answer(answer: str) -> bool:
    normalized = answer.lower()
    return "i do not have enough relevant evidence" in normalized or "no relevant context was retrieved" in normalized


def is_service_unavailable_answer(answer: str) -> bool:
    return "service is temporarily unavailable" in answer.lower()


def service_unavailable_answer(question: str) -> str:
    if wants_roman_urdu(question):
        return (
            "Dental AI service is temporarily unavailable. "
            "Meharbani karke thori dair baad dobara try karein. "
            "Agar dard, soojan, bukhar, bleeding, infection, ya treatment ka faisla ho to licensed dentist se rabta karein."
        )
    return (
        "Dental AI service is temporarily unavailable. Please try again shortly. "
        "For pain, swelling, fever, bleeding, infection, medication, diagnosis, or treatment decisions, consult a licensed dentist."
    )


def repair_patient_facing_answer(question: str, answer: str) -> str:
    if not is_leaked_or_template_answer(answer):
        return answer
    return "I do not have enough relevant evidence in the uploaded documents."


def is_leaked_or_template_answer(answer: str) -> bool:
    normalized = answer.lower()
    bad_patterns = [
        "[answer]",
        "[point 1]",
        "[safety note]",
        "[2-4 bullet points]",
        "[a note about safety]",
        "[explanation]",
        "then \"explanation",
        "then \"safety note",
        "we are to explain",
        "key points to cover",
        "we must emphasize",
        "do not mention backend",
        "do not claim the answer",
        "format:",
        "the user asked",
        "let's structure",
        "use exactly these headings",
        "start immediately with",
        "answer using the system instructions",
    ]
    if any(pattern in normalized for pattern in bad_patterns):
        return True
    if normalized.count("direct answer:") > 1:
        return True
    if "direct answer:" in normalized and len(re.sub(r"direct answer:\s*", "", normalized).strip()) < 30:
        return True
    return False


def is_current_info_question(question: str) -> bool:
    normalized = question.lower()
    triggers = [
        "latest", "current", "recent", "new guideline", "updated guideline",
        "2025", "2026", "today", "now", "new research", "official guideline",
        "recent study", "current recommendation",
    ]
    return any(trigger in normalized for trigger in triggers)


def normalize_rag_mode(mode: str | None) -> str:
    allowed = {"simple", "memory", "multi_query", "hyde", "adaptive", "corrective", "self_rag", "agentic"}
    normalized = (mode or "simple").lower().strip()
    return normalized if normalized in allowed else "simple"


def classify_query(question: str, filters: dict | None = None) -> str:
    filters = filters or {}
    normalized = question.lower()
    if filters.get("document_id"):
        return "document_specific"
    if wants_roman_urdu(question):
        return "roman_urdu"
    if any(term in normalized for term in ["swelling", "fever", "pus", "trauma", "bleeding", "severe pain", "trouble swallowing"]):
        return "emergency_safety"
    if any(term in normalized for term in ["pain", "dard", "toothache", "sensitivity", "infection", "soojan"]):
        return "symptom_guidance"
    if any(term in normalized for term in ["treatment", "medicine", "antibiotic", "dose", "prescribe", "extraction", "root canal"]):
        return "treatment_question"
    if any(term in normalized for term in ["upload", "document", "pdf", "source", "citation", "admin"]):
        return "admin_document_query"
    return "simple_dental_explanation"


def is_followup_question(question: str) -> bool:
    normalized = question.lower().strip()
    followup_terms = [
        "it", "this", "that", "they", "them", "same", "above", "previous", "explain more",
        "aur", "is ke", "iske", "us ke", "detail",
    ]
    return len(normalized.split()) <= 8 and any(term in normalized for term in followup_terms)


def generate_query_variants(question: str, max_variants: int = 4) -> list[str]:
    cleaned = re.sub(r"\s+", " ", question).strip()
    variants = [cleaned]
    subject = definition_subject_phrase(cleaned) if is_definition_question(cleaned) else ""
    if subject and subject != cleaned.lower():
        variants.append(subject)
    if len(variants) < max_variants:
        keywords = " ".join(sorted(question_keywords(cleaned)))
        if keywords and keywords not in variants:
            variants.append(keywords)
    deduped: list[str] = []
    for variant in variants:
        if variant and variant not in deduped:
            deduped.append(variant)
    return deduped[:max(1, max_variants)]


def merge_query_variants(primary: list[str], secondary: list[str], max_variants: int) -> list[str]:
    merged: list[str] = []
    for variant in [*primary, *secondary]:
        cleaned = re.sub(r"\s+", " ", str(variant or "")).strip()
        if cleaned and cleaned.lower() not in {item.lower() for item in merged}:
            merged.append(cleaned)
        if len(merged) >= max(1, max_variants):
            break
    return merged or primary[:max(1, max_variants)]


def rewrite_query_for_retrieval(question: str) -> str:
    cleaned = re.sub(r"\s+", " ", question).strip()
    if not cleaned:
        return cleaned
    expansions = []
    if is_definition_question(cleaned):
        subject = definition_subject_phrase(cleaned)
        if subject:
            expansions.append(subject)
    keywords = " ".join(sorted(question_keywords(cleaned)))
    if keywords:
        expansions.append(keywords)
    combined = " ".join([cleaned, *expansions])
    return re.sub(r"\s+", " ", combined).strip()[:900]


def retrieval_confidence(chunks: list[RetrievedChunk]) -> float:
    if not chunks:
        return 0.0
    scores = [float(chunk.metadata.get("query_relevance_score") or chunk.rerank_score or 0.0) for chunk in chunks[:3]]
    return sum(scores) / len(scores)


def contains_prescribing_language(answer: str) -> bool:
    normalized = answer.lower()
    prescribing_patterns = [
        r"\btake\s+\d+",
        r"\bmg\b",
        r"\btablet\b",
        r"\bprescribe\b",
        r"\bantibiotic\b.*\b(days?|daily|twice)\b",
    ]
    return any(re.search(pattern, normalized) for pattern in prescribing_patterns)


def needs_safety_note(question: str) -> bool:
    normalized = question.lower()
    return any(
        term in normalized
        for term in [
            "pain", "dard", "swelling", "fever", "bleeding", "pus", "trauma", "pregnancy",
            "child", "children", "medicine", "medication", "antibiotic", "dose", "infection",
        ]
    )


def enforce_safety_note(answer: str, question: str) -> str:
    if not needs_safety_note(question):
        return answer
    if "consult" in answer.lower() and "dentist" in answer.lower():
        return answer
    return (
        f"{answer.rstrip()}\n\n"
        "Safety Note: This is educational information only. For symptoms, diagnosis, medication, or treatment decisions, consult a licensed dentist."
    )


def answer_language_instruction(question: str) -> str:
    normalized = question.lower()
    if "roman urdu" in normalized or "hinglish" in normalized:
        return (
            "Roman Urdu means Urdu/Hindi words written with English letters only. "
            "Never use Urdu script or Arabic script for Roman Urdu."
        )
    if "urdu" in normalized:
        return "Respond in Urdu/Roman Urdu as requested by the user, using simple patient-friendly wording."
    return "Respond in the same language as the user's question when a language is explicitly requested."


def normalize_user_role(user_role: str | None) -> str:
    normalized = str(user_role or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"dentist", "specialist_dentist", "clinician", "doctor", "admin"}:
        return "dentist"
    if normalized in {"student", "dental_student"}:
        return "dental_student"
    return "patient"


def role_behavior_instruction(user_role: str | None) -> str:
    role = normalize_user_role(user_role)
    if role == "dentist":
        return (
            "The authenticated user is a dentist or clinical admin. Use a professional clinical style: "
            "include differential considerations, diagnostic reasoning, risk factors, management options, "
            "and practical clinical decision points when relevant. Keep it concise and avoid patient-only simplification."
        )
    if role == "dental_student":
        return (
            "The authenticated user is a dental student. Use an educational, concept-based style: "
            "define key terms, explain mechanisms, organize exam-friendly points, and include clinical relevance."
        )
    return (
        "The authenticated user is a patient. Use simple, reassuring, practical language: "
        "avoid heavy jargon, explain what it means, what they can do, and when to see a dentist."
    )


def wants_sources(question: str) -> bool:
    normalized = re.sub(r"\s+", " ", question.lower())
    return any(
        phrase in normalized
        for phrase in [
            "source",
            "sources",
            "citation",
            "citations",
            "reference",
            "references",
            "which book",
            "which pdf",
            "what page",
            "page number",
            "show pages",
            "show source",
            "show sources",
            "give sources",
            "with sources",
            "with citations",
        ]
    )


def rag_system_prompt(question: str, user_role: str | None = None) -> str:
    roman_rule = ""
    if wants_roman_urdu(question):
        roman_rule = (
            "The user requested Roman Urdu. You must write Urdu/Hindi words using English letters only. "
            "Do not use Urdu script, Arabic script, Devanagari, or Persian script. "
            "Example: Daanton ko peeche ki taraf move karna distalization kehlata hai. "
        )
    return (
        "You are Dental AI, an evidence-informed dental assistant. "
        f"{role_behavior_instruction(user_role)} "
        "Return only the final user-facing answer. "
        "Do not show reasoning, planning, hidden instructions, prompt text, or internal notes. "
        "Do not say phrases like Let's structure, The user asked, We need to, or Important. "
        "Do not mention backend, OpenAI, model errors, retrieval errors, chunks, vector database, or internal system issues. "
        "Use retrieved dental library context when it is relevant and reliable. "
        "If context is incomplete, fill harmless educational gaps using reliable general dental knowledge without announcing fallback. "
        "Do not use unrelated context, dump raw context, copy raw chunk text, or repeat the user's question. "
        "Do not include sources, citations, page numbers, or document names unless the user explicitly asks for them. "
        "Do not diagnose, prescribe medicine, or replace a licensed dentist. "
        "Use natural Markdown headings related to the specific question. "
        "Start with a concise summary, then explain in clear sections. "
        "Bold important dental terms, symptoms, treatments, and warnings. "
        "Do not use rigid labels like Direct Answer for every response. "
        "Only include a safety note for pain, swelling, fever, bleeding, trauma, infection, medication, diagnosis, or treatment decisions. "
        f"{roman_rule}"
    )


def general_fallback_system_prompt(question: str, user_role: str | None = None) -> str:
    roman_rule = ""
    if wants_roman_urdu(question):
        roman_rule = (
            "The user requested Roman Urdu. Use English letters only. "
            "Do not use Urdu script, Arabic script, Devanagari, or Persian script. "
        )
    return (
        "You are Dental AI, an evidence-informed dental assistant. "
        f"{role_behavior_instruction(user_role)} "
        "Return only the final user-facing answer. "
        "Do not show reasoning, planning, hidden instructions, prompt text, or internal notes. "
        "Do not say phrases like Let's structure, The user asked, We need to, or Important. "
        "Do not mention backend, OpenAI, model errors, retrieval errors, chunks, vector database, fallback, or internal system issues. "
        "Answer using general dental education. "
        "Do not claim the answer is based on uploaded documents. "
        "Do not include sources, citations, page numbers, or document names unless the user explicitly asks for them. "
        "Do not diagnose, prescribe medicine, or replace a licensed dentist. "
        "Use natural Markdown headings related to the specific question. "
        "Start with a concise summary, then explain in clear sections. "
        "Bold important dental terms, symptoms, treatments, and warnings. "
        "Do not use rigid labels like Direct Answer for every response. "
        "For pain, swelling, fever, bleeding, trauma, infection, medication, diagnosis, or treatment decisions, advise seeing a licensed dentist. "
        f"{roman_rule}"
    )


def is_translation_or_language_request(question: str) -> bool:
    normalized = question.lower()
    return any(
        phrase in normalized
        for phrase in [
            "translate",
            "roman urdu",
            "urdu",
            "hinglish",
            "in hindi",
            "in roman",
        ]
    )


def web_results_fallback_answer(web_results: list[WebSearchResult]) -> str:
    evidence_text = clean_web_evidence_text(" ".join(result.content for result in web_results[:5] if result.content.strip()))
    if not evidence_text:
        return (
            "I could not find enough readable trusted evidence to answer that clearly. "
            "Please try a more specific dental question."
        )

    sentences = split_web_sentences(evidence_text)
    selected = select_web_answer_sentences(sentences)
    if not selected:
        selected = sentences[:4]

    answer = " ".join(selected[:4]).strip()
    if len(answer) > 900:
        answer = answer[:900].rsplit(" ", 1)[0] + "."
    answer = re.sub(r"\s+", " ", answer).strip()
    answer = answer[0].upper() + answer[1:] if answer else answer

    return (
        f"{answer}\n\n"
        "For personal symptoms, diagnosis, or treatment decisions, consult a licensed dentist."
    )


def clean_web_evidence_text(text: str) -> str:
    cleaned = re.sub(r"#+\s*", " ", text)
    cleaned = re.sub(r"\[[^\]]+\]\([^)]+\)", " ", cleaned)
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = re.sub(r"\b(Back to top|Related Publications|Cover of|Internet)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def split_web_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    sentences = []
    for part in parts:
        sentence = part.strip(" -")
        if 35 <= len(sentence) <= 360 and not re.search(r"^(last update|next update|overview)\b", sentence, flags=re.IGNORECASE):
            sentences.append(sentence)
    return sentences


def select_web_answer_sentences(sentences: list[str]) -> list[str]:
    priority_patterns = [
        r"\btooth decay\b.*\b(caused|begins|is|called|cavity|cavities|caries)\b",
        r"\bbacteria\b.*\bacid",
        r"\benamel\b.*\bcavity",
        r"\bnot treated\b.*\b(pain|infection|tooth loss)\b",
        r"\bsee a dentist\b|\bconsult\b.*\bdentist\b",
    ]
    selected: list[str] = []
    for pattern in priority_patterns:
        for sentence in sentences:
            if sentence not in selected and re.search(pattern, sentence, flags=re.IGNORECASE):
                selected.append(sentence)
                break
    return selected


def generate_language_fallback_answer(question: str, chunks: list[RetrievedChunk]) -> str:
    if wants_roman_urdu(question):
        return (
            "LLM abhi available nahi hai, is liye main is Roman Urdu request ka reliable jawab generate nahi kar sakta. "
            "Qwen/Ollama connect hone ke baad main uploaded dental sources se proper Roman Urdu answer dunga."
        )

    return (
        "I could not reach the configured LLM to produce a reliable answer for this language request. "
        "Please try again after Qwen/Ollama is connected."
    )


def wants_roman_urdu(question: str) -> bool:
    normalized = question.lower()
    return "roman urdu" in normalized or "hinglish" in normalized or "in roman" in normalized


def contains_non_roman_script(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\u0900-\u097F]", text))


def strip_model_sources(answer: str) -> str:
    lines = answer.strip().splitlines()
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if lower in {"sources:", "source:", "citations:", "references:"}:
            break
        if re.match(r"^(source|sources|citation|citations|reference|references)\s*:", lower):
            break
        kept.append(line)
    cleaned = "\n".join(kept).strip()
    cleaned = re.sub(r"\((?:[^()]*?p(?:age)?\.?\s*\d+|[^()]*?page\s*\d+)[^()]*?\)", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def requested_translation_topic(question: str) -> str:
    cleaned = re.sub(
        r"\b(translate|into|in|roman|urdu|hinglish|the|significance|of)\b",
        " ",
        question,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "is concept"


GENERIC_RELEVANCE_TERMS = {
    "care",
    "clinical",
    "dental",
    "dentistry",
    "disease",
    "health",
    "literature",
    "medical",
    "medicine",
    "oral",
    "patient",
    "patients",
    "procedure",
    "reference",
    "surgery",
    "treatment",
}


BM25_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could", "do", "does",
    "for", "from", "give", "has", "have", "how", "in", "into", "is", "it", "its",
    "list", "me", "of", "on", "or", "please", "show", "summarize", "summary", "tell",
    "that", "the", "their", "this", "to", "type", "what", "when", "where", "which",
    "who", "why", "with", "about", "regarding",
}


def question_keywords(question: str) -> set[str]:
    return {
        normalize_lexical_token(token)
        for token in re.findall(r"[a-zA-Z][a-zA-Z-]{2,}", question.lower())
        if token not in BM25_STOPWORDS
    }


def bm25_tokens(text: str) -> list[str]:
    tokens = []
    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", text.lower()):
        normalized = normalize_lexical_token(token)
        if normalized and normalized not in BM25_STOPWORDS:
            tokens.append(normalized)
    return tokens


def bm25_scores(query_tokens: list[str], documents: list[list[str]], k1: float = 1.5, b: float = 0.75) -> list[float]:
    if not query_tokens or not documents:
        return []
    total_docs = len(documents)
    avg_doc_length = sum(len(document) for document in documents) / max(total_docs, 1)
    doc_freqs: Counter[str] = Counter()
    for document in documents:
        doc_freqs.update(set(document))

    scores: list[float] = []
    query_counts = Counter(query_tokens)
    for document in documents:
        term_counts = Counter(document)
        doc_length = max(len(document), 1)
        score = 0.0
        for term, query_count in query_counts.items():
            frequency = term_counts.get(term, 0)
            if frequency <= 0:
                continue
            idf = math.log(1 + (total_docs - doc_freqs[term] + 0.5) / (doc_freqs[term] + 0.5))
            denominator = frequency + k1 * (1 - b + b * doc_length / max(avg_doc_length, 1.0))
            score += idf * ((frequency * (k1 + 1)) / denominator) * query_count
        scores.append(round(score, 4))
    return scores


def chunk_search_text_from_payload(payload: dict) -> str:
    return " ".join(
        str(value or "")
        for value in [
            payload.get("text"),
            payload.get("book_title"),
            payload.get("title"),
            payload.get("document_name"),
            payload.get("section_title"),
            payload.get("chapter_title"),
            payload.get("dental_specialty"),
            payload.get("topic"),
        ]
    )


def normalize_lexical_token(token: str) -> str:
    token = token.lower().strip("-")
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ics"):
        return token[:-1]
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def core_question_terms(question: str) -> set[str]:
    return {term for term in question_keywords(question) if term not in GENERIC_RELEVANCE_TERMS}


def definition_subject_phrase(question: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9\s-]", " ", question.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(
        r"^(what\s+(is|are)|define|meaning\s+of|what\s+do\s+you\s+mean\s+by)\s+",
        "",
        normalized,
    )
    tokens = [
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z-]{2,}", normalized)
        if token not in {"the", "a", "an"}
    ]
    return " ".join(tokens)


def chunk_searchable_text(chunk: RetrievedChunk) -> str:
    metadata_text = " ".join(
        str(value)
        for key, value in chunk.metadata.items()
        if key
        in {
            "book_title",
            "chapter_title",
            "document_name",
            "section_title",
            "source",
            "specialty",
            "title",
            "topic",
        }
        and value
    )
    return f"{chunk.text} {chunk.citation.document_name or ''} {metadata_text}".lower()


def rank_sentences(sentences: list[str], keywords: set[str]) -> list[str]:
    def score(sentence: str) -> tuple[int, int]:
        sentence_l = sentence.lower()
        matches = sum(1 for keyword in keywords if keyword in sentence_l)
        phrase_matches = sum(1 for first, second in zip(sorted(keywords), sorted(keywords)[1:]) if f"{first} {second}" in sentence_l)
        return matches * 3 + phrase_matches, -len(sentence)

    return [sentence for sentence in sorted(sentences, key=score, reverse=True) if score(sentence)[0] > 0]


def is_noisy_sentence(sentence: str) -> bool:
    cleaned = sentence.strip()
    lower = cleaned.lower()
    if len(cleaned) > 450:
        return True
    if re.search(r"~|<{2,}|>{2,}|\"{2,}", cleaned):
        return True
    if re.search(r"\bfig\.?\s*(er|if|and|,)|\bcourtesy\s+dr\.|\bocclusal views\b", lower):
        return True
    if len(re.findall(r"\b[A-Za-z]{1,2}\b", cleaned)) > 12:
        return True
    quality = assess_chunk_quality(cleaned)
    return quality.is_noisy or quality.quality_score < 0.55


def build_qdrant_filter(filters: dict | None) -> qmodels.Filter | None:
    if not filters:
        return None

    must: list = []

    review_status = filters.get("review_status")
    if review_status:
        must.append(qmodels.FieldCondition(key="review_status", match=qmodels.MatchValue(value=review_status)))

    trust_levels = filters.get("trust_levels") or default_trust_levels(filters.get("user_role"))
    if trust_levels:
        must.append(qmodels.FieldCondition(key="trust_level", match=qmodels.MatchAny(any=trust_levels)))

    document_types = filters.get("document_types") or default_document_types(filters.get("user_role"))
    if document_types:
        must.append(qmodels.FieldCondition(key="document_type", match=qmodels.MatchAny(any=document_types)))

    min_year = filters.get("min_year")
    if min_year:
        must.append(qmodels.FieldCondition(key="year", range=qmodels.Range(gte=float(min_year))))

    document_id = filters.get("document_id")
    if document_id:
        must.append(qmodels.FieldCondition(key="document_id", match=qmodels.MatchValue(value=document_id)))

    payload_type = filters.get("payload_type")
    if payload_type:
        must.append(qmodels.FieldCondition(key="payload_type", match=qmodels.MatchValue(value=payload_type)))

    if not must:
        return None
    return qmodels.Filter(must=must)


def list_filter_values(value) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def default_trust_levels(user_role: str | None) -> list[str]:
    if user_role == "patient":
        return ["high", "medium"]
    return ["high", "medium"]


def default_document_types(user_role: str | None) -> list[str]:
    if user_role == "patient":
        return ["guideline", "patient_education", "textbook"]
    return ["guideline", "textbook", "patient_education", "research_article"]


def keyword_score(text: str, terms: set[str]) -> float:
    text_l = text.lower()
    score = 0.0
    for term in terms:
        occurrences = text_l.count(term)
        if occurrences:
            score += 1.0 + min(occurrences, 5) * 0.25
    phrase = " ".join(sorted(terms))
    if len(phrase) > 4 and phrase in text_l:
        score += 3.0
    return score


def merge_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    merged: dict[tuple[str, int | None, int | None], RetrievedChunk] = {}
    for chunk in chunks:
        key = (
            chunk.citation.document_id or chunk.citation.document_name,
            chunk.citation.page_number,
            chunk.citation.chunk_index,
        )
        existing = merged.get(key)
        if not existing:
            merged[key] = chunk
            continue
        existing.vector_score = max(existing.vector_score, chunk.vector_score)
        existing.keyword_score = max(existing.keyword_score, chunk.keyword_score)
        existing.citation.score = max(existing.vector_score, existing.keyword_score)
    return list(merged.values())


def rerank_chunks(question: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    terms = question_keywords(question)
    cross_scores = bge_rerank_scores(question, chunks)
    for chunk in chunks:
        trust_boost = {"high": 0.25, "medium": 0.1, "low": -0.25}.get(str(chunk.metadata.get("trust_level")), 0.0)
        review_boost = 0.2 if chunk.metadata.get("review_status") == "approved" else -0.2
        quality_score = float(chunk.metadata.get("quality_score", 1.0) or 0.0)
        quality_boost = (quality_score - 0.6) * 0.5
        lexical = keyword_score(chunk.text, terms)
        relevance = query_context_relevance_score(question, chunk)
        noise_penalty = -1.0 if chunk.metadata.get("is_noisy") else 0.0
        chunk.rerank_score = (
            chunk.vector_score
            + (chunk.keyword_score * 0.35)
            + (lexical * 0.2)
            + relevance
            + cross_scores.get(id(chunk), 0.0)
            + trust_boost
            + review_boost
            + quality_boost
            + noise_penalty
        )
        chunk.metadata["query_relevance_score"] = relevance
        chunk.citation.score = chunk.rerank_score
    return sorted(chunks, key=lambda item: item.rerank_score, reverse=True)


def bge_rerank_scores(question: str, chunks: list[RetrievedChunk]) -> dict[int, float]:
    settings = get_settings()
    if not settings.enable_bge_reranker or not chunks:
        return {}
    model = get_bge_reranker(settings.bge_reranker_model)
    if model is None:
        return {}
    try:
        pairs = [(question, chunk.text[:1600]) for chunk in chunks[:40]]
        raw_scores = model.predict(pairs)
    except Exception:
        logger.exception("rag.bge_reranker.failed")
        return {}
    scores = [float(score) for score in raw_scores]
    if not scores:
        return {}
    min_score = min(scores)
    max_score = max(scores)
    spread = max(max_score - min_score, 1e-6)
    return {
        id(chunk): ((score - min_score) / spread) * 1.25
        for chunk, score in zip(chunks[:40], scores)
    }


@lru_cache(maxsize=2)
def get_bge_reranker(model_name: str):
    try:
        from sentence_transformers import CrossEncoder
    except Exception:
        logger.warning("rag.bge_reranker.unavailable")
        return None
    try:
        return CrossEncoder(model_name)
    except Exception:
        logger.exception("rag.bge_reranker.load_failed")
        return None


def query_context_relevance_score(question: str, chunk: RetrievedChunk) -> float:
    terms = sorted(question_keywords(question))
    if not terms:
        return 0.0
    text_l = chunk_searchable_text(chunk)
    matches = [term for term in terms if term in text_l]
    coverage = len(matches) / len(terms)
    lexical = min(keyword_score(chunk.text, set(terms)), 6.0) * 0.25
    phrase_bonus = 0.0
    normalized_question_terms = [term for term in re.findall(r"[a-zA-Z][a-zA-Z-]{2,}", question.lower()) if term in terms]
    for first, second in zip(normalized_question_terms, normalized_question_terms[1:]):
        if f"{first} {second}" in text_l:
            phrase_bonus += 0.35
    vector_boost = max(0.0, chunk.vector_score - 0.35) * 0.8
    quality_score = float(chunk.metadata.get("quality_score", 1.0) or 0.0)
    quality_boost = max(0.0, quality_score - 0.6) * 0.3
    return round((coverage * 2.0) + lexical + min(phrase_bonus, 1.0) + vector_boost + quality_boost, 3)


def is_relevant_chunk(question: str, chunk: RetrievedChunk, min_score: float) -> bool:
    terms = question_keywords(question)
    if not terms:
        return chunk.rerank_score >= min_score
    text_l = chunk_searchable_text(chunk)
    matched_terms = {term for term in terms if term in text_l}
    core_terms = core_question_terms(question)
    matched_core_terms = {term for term in core_terms if term in text_l}
    if core_terms:
        if is_definition_question(question):
            subject_phrase = definition_subject_phrase(question)
            if subject_phrase and len(subject_phrase.split()) > 1 and any(term in core_terms for term in subject_phrase.split()):
                if subject_phrase not in text_l:
                    return False
            if not matched_core_terms:
                return False
        if len(core_terms) <= 2 and not matched_core_terms:
            return False
        if len(core_terms) >= 3 and (len(matched_core_terms) / len(core_terms)) < 0.4:
            return False
    min_matches = 2 if len(terms) >= 3 else 1
    coverage = len(matched_terms) / len(terms)
    relevance = float(chunk.metadata.get("query_relevance_score") or query_context_relevance_score(question, chunk))
    if relevance < min_score:
        return False
    if len(matched_terms) < min_matches and coverage < 0.5:
        return False
    if is_noisy_context_block(chunk.text):
        return False
    return True


def filter_chunks_for_question(question: str, chunks: list[RetrievedChunk], allow_noisy: bool = False) -> list[RetrievedChunk]:
    return [chunk for chunk in chunks if should_use_chunk(question, chunk, allow_noisy=allow_noisy)]


def should_use_chunk(question: str, chunk: RetrievedChunk, allow_noisy: bool = False) -> bool:
    if chunk.metadata.get("payload_type") == "visual":
        return False
    if is_removed_cleanup_document(chunk):
        return False
    quality = assess_chunk_quality(chunk.text)
    metadata_noisy = bool(chunk.metadata.get("is_noisy", quality.is_noisy))
    quality_score = float(chunk.metadata.get("quality_score", quality.quality_score) or 0.0)
    reasons = chunk.metadata.get("noise_reasons") or quality.noise_reasons
    if isinstance(reasons, str):
        reasons_l = reasons.lower()
    else:
        reasons_l = " ".join(str(reason).lower() for reason in reasons)

    if allow_noisy:
        return quality_score >= 0.1

    if metadata_noisy or quality_score < 0.6:
        return False
    if any(term in reasons_l for term in ["questionnaire", "form", "h17040", "reference_index", "bibliography"]):
        return False
    if is_noisy_context_block(chunk.text):
        return False
    if is_form_or_survey_question(chunk.text) and not is_form_or_survey_question(question):
        return False
    return True


def rerank_visuals(question: str, visuals: list[RetrievedVisual], chunks: list[RetrievedChunk]) -> list[RetrievedVisual]:
    terms = question_keywords(question)
    chunk_pages = {
        (chunk.citation.document_id, chunk.citation.page_number)
        for chunk in chunks
        if chunk.citation.document_id and chunk.citation.page_number
    }
    related_chunk_ids = {
        str(chunk.metadata.get("chunk_id") or chunk.metadata.get("qdrant_point_id"))
        for chunk in chunks
        if chunk.metadata.get("chunk_id") or chunk.metadata.get("qdrant_point_id")
    }
    for visual in visuals:
        text = visual_searchable_text(visual)
        lexical = keyword_score(text, terms)
        type_boost = 0.5 if wants_visual_answer(question) else 0.0
        page_boost = 0.45 if (visual.citation.document_id, visual.citation.page_number) in chunk_pages else 0.0
        related_ids = {str(item) for item in visual.metadata.get("related_chunk_ids") or []}
        relation_boost = 0.55 if related_ids and related_ids.intersection(related_chunk_ids) else 0.0
        caption_boost = 0.25 if visual.citation.caption_text else 0.0
        quality = float(visual.metadata.get("quality_score") or 0.0)
        quality_boost = max(0.0, quality - 0.45) * 0.45
        visual.rerank_score = (
            visual.vector_score
            + lexical * 0.18
            + type_boost
            + page_boost
            + relation_boost
            + caption_boost
            + quality_boost
        )
        visual.citation.score = visual.rerank_score
    return sorted(visuals, key=lambda item: item.rerank_score, reverse=True)


def merge_visuals(visuals: list[RetrievedVisual]) -> list[RetrievedVisual]:
    merged: dict[str, RetrievedVisual] = {}
    for visual in visuals:
        key = visual.citation.visual_id or visual.metadata.get("qdrant_point_id") or visual.citation.image_path
        if not key:
            continue
        existing = merged.get(str(key))
        if not existing:
            merged[str(key)] = visual
            continue
        existing.vector_score = max(existing.vector_score, visual.vector_score)
        existing.metadata["related_chunk_ids"] = sorted(
            {
                *[str(item) for item in existing.metadata.get("related_chunk_ids") or []],
                *[str(item) for item in visual.metadata.get("related_chunk_ids") or []],
            }
        )
        if not existing.citation.caption_text and visual.citation.caption_text:
            existing.citation.caption_text = visual.citation.caption_text
        if not existing.citation.generated_description and visual.citation.generated_description:
            existing.citation.generated_description = visual.citation.generated_description
    return list(merged.values())


def parse_related_chunk_ids(value: str | list | None) -> set[str]:
    if not value:
        return set()
    if isinstance(value, list):
        return {str(item) for item in value if item}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {item.strip() for item in str(value).split(",") if item.strip()}
    if isinstance(parsed, list):
        return {str(item) for item in parsed if item}
    return set()


def visual_searchable_text(visual: RetrievedVisual) -> str:
    return " ".join(
        str(value or "")
        for value in [
            visual.citation.caption_text,
            visual.citation.generated_description,
            visual.metadata.get("nearby_text"),
            visual.citation.visual_type,
            visual.citation.document_name,
        ]
    ).lower()


def visual_search_text_from_payload(payload: dict) -> str:
    return " ".join(
        str(value or "")
        for value in [
            payload.get("caption_text"),
            payload.get("nearby_text"),
            payload.get("generated_description"),
            payload.get("visual_type"),
            payload.get("document_name"),
        ]
    )


def wants_visual_answer(question: str) -> bool:
    if wants_no_visual_answer(question):
        return False
    normalized = question.lower()
    return any(
        term in normalized
        for term in [
            "figure",
            "fig.",
            "image",
            "picture",
            "diagram",
            "chart",
            "flowchart",
            "table",
            "visual",
            "show",
            "graph",
        ]
    )


def wants_no_visual_answer(question: str) -> bool:
    normalized = re.sub(r"\s+", " ", question.lower())
    no_visual_patterns = [
        "without showing a figure",
        "without figure",
        "without figures",
        "without image",
        "without images",
        "without visual",
        "without visuals",
        "do not show image",
        "do not show images",
        "do not show a figure",
        "do not show figures",
        "dont show image",
        "dont show images",
        "dont show figure",
        "don't show image",
        "don't show images",
        "don't show figure",
        "avoid figure",
        "avoid figures",
        "avoid image",
        "avoid images",
        "text-only",
        "text only",
        "text evidence only",
        "evidence only",
    ]
    return any(pattern in normalized for pattern in no_visual_patterns)


def image_url_for_visual_path(image_path: str) -> str:
    normalized = image_path.replace("\\", "/")
    marker = "uploads/"
    index = normalized.find(marker)
    if index >= 0:
        return "/" + normalized[index:]
    return "/" + normalized.lstrip("/")


def is_removed_cleanup_document(chunk: RetrievedChunk) -> bool:
    document_id = str(chunk.metadata.get("document_id") or chunk.citation.document_id or "")
    return bool(document_id and document_id in removed_cleanup_document_ids())


@lru_cache(maxsize=1)
def removed_cleanup_document_ids() -> set[str]:
    summary_path = Path("cleanup_reports") / "applied_cleanup_summary.json"
    if not summary_path.exists():
        return set()
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {
        str(item.get("document_id"))
        for item in data.get("documents", [])
        if item.get("document_id")
    }


def is_noisy_context_block(text: str) -> bool:
    lower = text.lower()
    if re.search(r"\b(references|bibliography|index)\b.{0,120}\b(pp\.|vol\.|doi|et al\.|isbn)\b", lower):
        return True
    if re.search(r"\b(table|questionnaire|survey form|appendix|annex)\b", lower) and symbol_or_digit_density(text) > 0.28:
        return True
    if len(re.findall(r"\b\d+(?:\.\d+)?%?\b", text)) >= 18:
        return True
    if len(re.findall(r"\bet al\.|\bdoi\b|\bISBN\b|https?://", text, flags=re.IGNORECASE)) >= 4:
        return True
    return False


def symbol_or_digit_density(text: str) -> float:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return 1.0
    return sum(1 for char in compact if not char.isalpha()) / len(compact)


def compress_context(question: str, text: str) -> str:
    terms = question_keywords(question)
    cleaned = clean_context_text(text)
    sentences = split_sentences(cleaned)
    if not sentences:
        return ""
    ranked = rank_sentences(sentences, terms)
    selected = ranked[:5] if ranked else []
    compressed = " ".join(selected).strip()
    if len(compressed) > 1000:
        compressed = compressed[:1000].rsplit(" ", 1)[0] + "."
    return compressed


def clean_context_text(text: str) -> str:
    cleaned = re.sub(r"BM\.indd\s+\d+\s+\d+/\d+/\d+\s+\d+:\d+:\d+\s+[AP]M", " ", text)
    cleaned = re.sub(r"\bPlate\s+\d+\b", " ", cleaned)
    cleaned = re.sub(r"\bAnnex\s+\d+\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def extract_code_answer(question: str, context: str) -> str | None:
    match = re.search(r"\bcode\s+([a-z0-9]+)\b", question.lower())
    if not match:
        return None
    code = re.escape(match.group(1))
    cleaned = clean_context_text(context)
    patterns = [
        rf"Code\s+{code}\s*:\s*([^.;]+)",
        rf"Code\s+{code}\s+and\s+code\s+[a-z0-9]+\s*:\s*([^.;]+)",
        rf"Code\s+[a-z0-9]+\s+and\s+code\s+{code}\s*:\s*([^.;]+)",
    ]
    findings: list[str] = []
    for pattern in patterns:
        for found in re.findall(pattern, cleaned, flags=re.IGNORECASE):
            finding = found.strip(" ,:-")
            if finding and finding.lower() not in {item.lower() for item in findings}:
                findings.append(finding)
    if not findings:
        return None
    bullets = "\n".join(f"- Code {match.group(1).upper()}: {finding}" for finding in findings[:5])
    return f"The retrieved evidence mentions:\n\n{bullets}"


def dedupe_citations(citations: list[SourceCitation]) -> list[SourceCitation]:
    seen: set[tuple[str, int | None, int | None]] = set()
    unique: list[SourceCitation] = []
    for citation in citations:
        key = (citation.document_name, citation.page_number, citation.chunk_index)
        if key in seen:
            continue
        seen.add(key)
        unique.append(citation)
    return unique
