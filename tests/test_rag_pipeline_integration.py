"""Phase 6: integration test for the full retrieval -> generation -> citation-verification
pipeline against a real (embedded, in-memory) Qdrant collection.

What's real here: Qdrant itself (qdrant-client's in-memory mode - no network, no external
service, but the actual vector search / filtering / query_points code path), the
embedding model (HashingEmbeddingModel - already this codebase's own deterministic
fallback, see app/services/embeddings.py, chosen here so the test needs no ML model
download and stays fast/hermetic), RAGService.retrieve() end to end (vector search,
role-based trust_level/document_type filtering, relevance gating, reranking,
compression), and the real graph node functions build_context / generate_answer /
validate_citations from app/agent/graph.py and app/agent/nodes/planner.py.

What's stubbed: only the LLM call itself (LLMService.generate) - there's no Ollama in CI,
and this test's job is to prove the surrounding pipeline wiring is correct, not to
evaluate model output quality (that's scripts/evaluate_rag.py's job, run separately
against docs/evaluation_dataset.jsonl).

Two cases: an answer that's actually grounded in the retrieved chunks should survive
citation verification untouched; an answer that fabricates an unsupported claim should
get caught by it (app/agent/nodes/citation_verifier.py's per-sentence lexical-support
check) - this is the concrete regression test for the non-negotiable constraint that
citation verification never gets silently relaxed.
"""

from typing import Any

import pytest
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.agent.graph import generate_answer
from app.agent.nodes.planner import build_context, validate_citations
from app.agent.state import AgentState
from app.services.embeddings import HashingEmbeddingModel
from app.services.rag import RAGService
from app.services.vector_store import ResilientQdrantClient

COLLECTION = "dental_docs_test"
VECTOR_SIZE = 384

FIXTURE_CHUNKS: list[dict[str, str | int]] = [
    {
        "document_id": "doc-who-oral-health",
        "document_name": "WHO Oral Health Guide",
        "chunk_index": 1,
        "page_number": 12,
        "text": (
            "Dental caries, commonly called tooth decay or cavities, develops when "
            "bacteria in the mouth produce acid from sugars and starches in food, and "
            "this acid gradually erodes and destroys the hard enamel surface of the tooth."
        ),
    },
    {
        "document_id": "doc-who-oral-health",
        "document_name": "WHO Oral Health Guide",
        "chunk_index": 2,
        "page_number": 13,
        "text": (
            "Frequent snacking on sugary foods and drinks increases the risk of dental "
            "caries because it gives mouth bacteria more opportunities to produce the "
            "acid that damages tooth enamel."
        ),
    },
    {
        "document_id": "doc-patient-handbook",
        "document_name": "Patient Education Handbook",
        "chunk_index": 4,
        "page_number": 4,
        "text": (
            "Brushing twice daily with fluoride toothpaste helps prevent tooth decay "
            "because fluoride strengthens enamel and makes it more resistant to the acid "
            "produced by decay-causing bacteria."
        ),
    },
    {
        # Distractor: shares no vocabulary with the test question and must not surface
        # in the retrieved/answered result.
        "document_id": "doc-oral-surgery",
        "document_name": "Oral Surgery Manual",
        "chunk_index": 88,
        "page_number": 88,
        "text": (
            "Impacted wisdom teeth that cause repeated infection or crowding are "
            "typically recommended for surgical extraction under local or general "
            "anesthesia."
        ),
    },
]

QUESTION = "What causes tooth decay?"


def _seed_qdrant(embedding_model: HashingEmbeddingModel) -> ResilientQdrantClient:
    raw_client = QdrantClient(":memory:")
    raw_client.create_collection(
        collection_name=COLLECTION,
        vectors_config=qmodels.VectorParams(size=VECTOR_SIZE, distance=qmodels.Distance.COSINE),
    )
    points: list[qmodels.PointStruct] = []
    for i, fixture in enumerate(FIXTURE_CHUNKS):
        text = str(fixture["text"])
        vector = embedding_model.encode([text])[0].tolist()
        points.append(
            qmodels.PointStruct(
                id=i + 1,
                vector=vector,
                payload={
                    "payload_type": "text",
                    "text": text,
                    "document_id": fixture["document_id"],
                    "document_name": fixture["document_name"],
                    "book_title": fixture["document_name"],
                    "chunk_index": fixture["chunk_index"],
                    "page_number": fixture["page_number"],
                    "trust_level": "high",
                    "document_type": "patient_education",
                    "review_status": "approved",
                },
            )
        )
    raw_client.upsert(collection_name=COLLECTION, points=points)
    return ResilientQdrantClient(raw_client, max_attempts=1)


def _retrieve_real_chunks(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    embedding_model = HashingEmbeddingModel(dimensions=VECTOR_SIZE)
    qdrant = _seed_qdrant(embedding_model)

    monkeypatch.setattr("app.services.rag.get_embedding_model", lambda: embedding_model)
    monkeypatch.setattr("app.services.rag.get_qdrant_client", lambda: qdrant)

    rag = RAGService()
    monkeypatch.setattr(rag.settings, "qdrant_collection", COLLECTION)
    # Force the embedded/local query_points code path in qdrant_vector_search_compatible()
    # rather than the legacy REST client, which would otherwise try to reach a real
    # qdrant_url over the network.
    monkeypatch.setattr(rag.settings, "qdrant_url", "")
    # Keyword search hits Postgres (fetch_bm25_candidates), independent of Qdrant - out of
    # scope for this test, which is specifically about the Qdrant-backed vector path.
    monkeypatch.setattr(rag.settings, "enable_keyword_search", False)
    monkeypatch.setattr(rag.settings, "enable_adjacent_chunk_expansion", False)

    retrieved = rag.retrieve(QUESTION, filters={"user_role": "patient"})
    return [
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
        for chunk in retrieved
    ]


def test_retrieval_returns_relevant_seeded_chunks_and_excludes_distractor(monkeypatch):
    chunks = _retrieve_real_chunks(monkeypatch)

    assert chunks, "expected the real Qdrant-backed retrieval to return seeded chunks"
    document_names = {c["citation"]["document_name"] for c in chunks}
    assert "Oral Surgery Manual" not in document_names, (
        "unrelated wisdom-teeth chunk should not be judged relevant to a tooth-decay question"
    )
    assert document_names & {"WHO Oral Health Guide", "Patient Education Handbook"}


def test_grounded_answer_survives_citation_verification(monkeypatch):
    chunks = _retrieve_real_chunks(monkeypatch)
    assert chunks

    state = AgentState(question=QUESTION, user_role="patient", retrieved_chunks=chunks)
    build_context(state)
    assert state.context_text, "context builder should produce non-empty context from real retrieved chunks"

    grounded_answer = (
        "Tooth decay is caused by bacteria in the mouth that produce acid from sugars "
        "and starches in food, and this acid erodes the tooth's enamel. Frequent "
        "snacking on sugary foods increases this risk, while fluoride toothpaste helps "
        "prevent decay by strengthening enamel against the acid."
    )

    class FakeLLM:
        def generate(self, prompt, *, system_prompt, **kwargs):
            return grounded_answer

    monkeypatch.setattr("app.services.llm.LLMService", FakeLLM)
    generate_answer(state)
    validate_citations(state)

    assert state.error is None
    assert "erodes" in state.answer or "acid" in state.answer
    assert state.sources, "a grounded, chunk-citing answer should retain sources after verification"


def test_hallucinated_claim_is_caught_by_citation_verification(monkeypatch):
    chunks = _retrieve_real_chunks(monkeypatch)
    assert chunks

    state = AgentState(question=QUESTION, user_role="patient", retrieved_chunks=chunks)
    build_context(state)
    assert state.context_text

    # citation_verifier.py only rewrites state.answer when enough grounded sentences
    # remain after trimming (more than 3) - for a short answer it flags the issue
    # internally (the CITATION_VERIFICATION_TOTAL metric, result="flagged_but_kept") but
    # leaves the visible text untouched rather than risk gutting a short reply down to
    # almost nothing. That's pre-existing behavior this hardening pass didn't touch, not
    # something to test around - see test_short_hallucinated_answer_is_flagged_but_not_edited
    # below for that path. This test uses enough grounded sentences that the fabricated
    # one is actually trimmed, which is the common case for this product's answer length.
    hallucinated_answer = (
        "Tooth decay is caused by bacteria in the mouth that produce acid from sugars "
        "and starches in food. This acid gradually erodes and destroys the hard enamel "
        "surface of the tooth. Frequent snacking on sugary foods and drinks increases "
        "this risk by giving bacteria more chances to produce acid. Brushing twice daily "
        "with fluoride toothpaste helps prevent decay because fluoride strengthens "
        "enamel against acid attack. Drinking cold water in winter causes cavities "
        "directly, and applying garlic paste overnight can completely cure existing "
        "tooth decay without any dental treatment."
    )

    class FakeLLM:
        def generate(self, prompt, *, system_prompt, **kwargs):
            return hallucinated_answer

    monkeypatch.setattr("app.services.llm.LLMService", FakeLLM)
    generate_answer(state)

    assert "garlic paste" in state.answer, "sanity check: fabricated sentence present before verification"

    validate_citations(state)

    assert "garlic paste" not in state.answer, (
        "citation verifier should have removed the unsupported garlic-paste claim"
    )
    assert "cold water" not in state.answer
    assert "fluoride" in state.answer, "grounded sentences should survive verification"


def test_short_hallucinated_answer_is_flagged_but_not_edited(monkeypatch):
    """Documents a real, pre-existing limit rather than hiding it: verify_citations()
    only rewrites state.answer if more than 3 sentences remain after trimming (see
    app/agent/nodes/citation_verifier.py). A short answer with one fabricated sentence
    is detected (traced, and CITATION_VERIFICATION_TOTAL{result="flagged_but_kept"} fires)
    but the fabricated sentence still reaches the user untouched. Flagging this as a
    product/policy question rather than silently deciding it: should short answers with
    an unsupported claim be blocked/regenerated instead of shipped with a silent flag?"""
    chunks = _retrieve_real_chunks(monkeypatch)
    assert chunks

    state = AgentState(question=QUESTION, user_role="patient", retrieved_chunks=chunks)
    build_context(state)

    short_hallucinated_answer = (
        "Tooth decay is caused by bacteria that produce acid from sugars, which erodes "
        "enamel over time. Applying garlic paste overnight can completely cure existing "
        "tooth decay without any dental treatment."
    )

    class FakeLLM:
        def generate(self, prompt, *, system_prompt, **kwargs):
            return short_hallucinated_answer

    monkeypatch.setattr("app.services.llm.LLMService", FakeLLM)
    generate_answer(state)
    validate_citations(state)

    citation_trace = next(t for t in state.trace_log if t["node"] == "citation_verifier")
    assert "flagged but too few remaining" in citation_trace["detail"]
    assert "garlic paste" in state.answer
