from app.schemas import SourceCitation
from app.services.chunk_quality import assess_chunk_quality
from app.services.evaluation import EvaluationCase, evaluate_cases, summarize_results
from app.services.ingestion import clean_pdf_text
from app.services.rag import RAGService, RetrievedChunk, build_qdrant_filter, keyword_score, rerank_chunks, should_use_chunk


def test_clean_pdf_text_removes_artifacts_and_repairs_words():
    text = clean_pdf_text("Chapter 1\nBM.indd 42\ncar- ies is preventable.\nPlate 12\n")

    assert "BM.indd" not in text
    assert "Plate" not in text
    assert "caries" in text


def test_chunk_quality_detects_h17040_questionnaire_noise():
    quality = assess_chunk_quality(
        "/H17040 Put a tick/cross. How often do you clean your teeth? "
        "Never Fairly often Very often Sometimes Don't know."
    )

    assert quality.is_noisy
    assert quality.quality_score < 0.6
    assert "who_form_artifact_h17040" in quality.noise_reasons
    assert "questionnaire_scale_options" in quality.noise_reasons


def test_normal_retrieval_rejects_noisy_questionnaire_chunk():
    noisy = RetrievedChunk(
        text="/H17040 Put a tick/cross. Never Fairly often Very often Sometimes Don't know.",
        citation=SourceCitation(document_name="WHO Survey", page_number=122, chunk_index=4),
        metadata={"is_noisy": True, "quality_score": 0.2, "noise_reasons": ["questionnaire_or_form_text"]},
    )

    assert not should_use_chunk("what you know about oral medicines", noisy)
    assert should_use_chunk("what does the oral health survey form ask?", noisy, allow_noisy=True)


def test_metadata_filter_builds_trusted_approved_constraints():
    qdrant_filter = build_qdrant_filter(
        {
            "review_status": "approved",
            "trust_levels": ["high", "medium"],
            "document_types": ["guideline", "textbook"],
            "min_year": 2015,
        }
    )

    assert qdrant_filter is not None
    assert len(qdrant_filter.must) == 4


def test_keyword_score_and_reranker_promote_exact_terms_and_trust():
    low_trust = RetrievedChunk(
        text="General information about dental disease.",
        citation=SourceCitation(document_name="Old notes", page_number=1, chunk_index=1),
        metadata={"trust_level": "low", "review_status": "unreviewed"},
        vector_score=0.7,
    )
    exact_high_trust = RetrievedChunk(
        text="ICDAS code 1 describes an early enamel lesion.",
        citation=SourceCitation(document_name="Guideline", page_number=10, chunk_index=2),
        metadata={"trust_level": "high", "review_status": "approved"},
        vector_score=0.6,
        keyword_score=keyword_score("ICDAS code 1 describes an early enamel lesion.", {"icdas", "code", "enamel"}),
    )

    ranked = rerank_chunks("What is ICDAS code 1?", [low_trust, exact_high_trust])

    assert ranked[0].citation.document_name == "Guideline"


def test_evaluation_scores_terms_citations_and_sources():
    class FakeService:
        def answer(self, question, top_k=None, filters=None):
            return (
                "Dental caries is a biofilm-mediated disease.",
                [SourceCitation(document_name="Dental Caries Textbook", page_number=54, chunk_index=12)],
            )

    results = evaluate_cases(
        FakeService(),
        [
            EvaluationCase(
                question="What is tooth decay?",
                expected_terms=["caries", "biofilm"],
                expected_sources=["caries textbook"],
            )
        ],
    )
    summary = summarize_results(results)

    assert results[0].passed
    assert summary["pass_rate"] == 1.0


def test_openai_error_falls_back_to_extractive_answer():
    from openai import RateLimitError
    import httpx

    class FakeCompletions:
        def create(self, **kwargs):
            response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))
            raise RateLimitError("quota exceeded", response=response, body={"error": {"code": "insufficient_quota"}})

    class FakeClient:
        class Chat:
            completions = FakeCompletions()

        chat = Chat()

    service = object.__new__(RAGService)
    service.openai_client = FakeClient()
    service.settings = type("Settings", (), {"openai_model": "gpt-test"})()
    chunks = [
        RetrievedChunk(
            text="Oral and maxillofacial injuries can involve the oral cavity, teeth, jaws, and surrounding soft tissues.",
            citation=SourceCitation(document_name="Oral Surgery", page_number=10, chunk_index=1),
            metadata={"trust_level": "high", "review_status": "approved", "quality_score": 0.9},
        )
    ]

    answer = service.generate_answer("Oral and maxillofacial injuries oral cavity", chunks)

    assert "Based on the uploaded dental references" in answer
    assert "maxillofacial injuries" in answer
