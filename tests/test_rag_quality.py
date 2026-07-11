from app.schemas import SourceCitation, VisualCitation
from app.services.llm import LLMGenerationError
from app.services.web_search import WebSearchResult
from app.services.chunk_quality import assess_chunk_quality
from app.services.evaluation import EvaluationCase, evaluate_cases, summarize_results
from app.services.ingestion import clean_pdf_text
from app.services.rag import (
    RAGService,
    RetrievedChunk,
    RetrievedVisual,
    build_qdrant_filter,
    classify_query,
    generate_query_variants,
    is_relevant_chunk,
    keyword_score,
    rerank_chunks,
    should_use_chunk,
    repair_patient_facing_answer,
    web_results_fallback_answer,
)


class StubRagSettings:
    rag_mode = "simple"
    allow_general_fallback = True
    enable_memory = True
    enable_hyde = False
    enable_self_check = False
    retrieval_top_k = 5
    retrieval_min_relevance_score = 1.1
    multi_query_max_variants = 4
    enable_multimodal_rag = True
    visual_min_relevance_score = 0.95


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


def test_relevance_gate_rejects_unrelated_orthodontic_chunk_for_publisher_query():
    chunk = RetrievedChunk(
        text="Orthodontic brackets and wires move teeth through continuous pressure.",
        citation=SourceCitation(document_name="Orthodontics", page_number=1, chunk_index=1),
        metadata={"trust_level": "high", "review_status": "approved", "quality_score": 0.9},
        vector_score=0.4,
    )

    ranked = rerank_chunks("Summarize the responsibility of publishers in medical literature.", [chunk])

    assert not is_relevant_chunk(
        "Summarize the responsibility of publishers in medical literature.",
        ranked[0],
        min_score=1.1,
    )


def test_definition_relevance_requires_core_subject_term():
    chunk = RetrievedChunk(
        text=(
            "An arbitrary articulator is satisfactory for establishing dental relationships "
            "that result from mandibular ramus surgery without maxillary surgery."
        ),
        citation=SourceCitation(document_name="Orthodontic Surgery", page_number=168, chunk_index=3),
        metadata={"trust_level": "high", "review_status": "approved", "quality_score": 0.9},
        vector_score=0.75,
    )

    ranked = rerank_chunks("What is maxillofacial surgery?", [chunk])

    assert not is_relevant_chunk("What is maxillofacial surgery?", ranked[0], min_score=1.1)


def test_definition_relevance_accepts_direct_subject_term():
    chunk = RetrievedChunk(
        text=(
            "Oral and maxillofacial surgery is a dental surgical specialty that manages "
            "conditions affecting the jaws, mouth, face, and related structures."
        ),
        citation=SourceCitation(document_name="Oral Surgery", page_number=12, chunk_index=1),
        metadata={"trust_level": "high", "review_status": "approved", "quality_score": 0.9},
        vector_score=0.75,
    )

    ranked = rerank_chunks("What is maxillofacial surgery?", [chunk])

    assert is_relevant_chunk("What is maxillofacial surgery?", ranked[0], min_score=1.1)


def test_definition_relevance_rejects_nearby_but_different_subject():
    chunk = RetrievedChunk(
        text="Oral and maxillofacial injuries can involve the oral cavity, teeth, jaws, and surrounding soft tissues.",
        citation=SourceCitation(document_name="Oral Surgery", page_number=10, chunk_index=1),
        metadata={"trust_level": "high", "review_status": "approved", "quality_score": 0.9},
        vector_score=0.75,
    )

    ranked = rerank_chunks("What is maxillofacial surgery?", [chunk])

    assert not is_relevant_chunk("What is maxillofacial surgery?", ranked[0], min_score=1.1)


def test_multi_query_variants_add_clinical_terms():
    variants = generate_query_variants("What causes tooth decay?", max_variants=4)

    assert variants[0] == "What causes tooth decay?"
    assert len(variants) > 1
    assert any("tooth" in variant.lower() or "decay" in variant.lower() for variant in variants)


def test_memory_context_uses_relevant_recent_history():
    service = object.__new__(RAGService)
    service.settings = StubRagSettings()
    history = [
        {"role": "user", "content": "Tell me about dental caries prevention."},
        {"role": "assistant", "content": "Dental caries prevention includes fluoride and sugar control."},
        {"role": "user", "content": "Unrelated billing question."},
    ]

    memory = service.build_memory_context("Explain caries risk.", history)

    assert "dental caries prevention" in memory.lower()
    assert "billing" not in memory.lower()


def test_retrieve_for_mode_passes_memory_to_retrieval():
    service = object.__new__(RAGService)
    service.settings = StubRagSettings()
    captured = {}

    def fake_retrieve(question, top_k=None, filters=None):
        captured["question"] = question
        return []

    service.retrieve = fake_retrieve

    service.retrieve_for_mode(
        "Explain caries risk.",
        filters={"conversation_history": [{"role": "user", "content": "Dental caries prevention history."}]},
    )

    assert "Relevant conversation memory" in captured["question"]
    assert "Dental caries prevention history" in captured["question"]


def test_multi_query_retrieval_uses_generated_variants():
    service = object.__new__(RAGService)
    service.settings = StubRagSettings()
    calls = []
    chunk = RetrievedChunk(
        text="Tooth decay is also called dental caries and involves enamel demineralization.",
        citation=SourceCitation(document_name="Dental Caries", page_number=1, chunk_index=1),
        metadata={"trust_level": "high", "review_status": "approved", "quality_score": 0.9},
        vector_score=0.8,
    )

    def fake_retrieve(question, top_k=None, filters=None):
        calls.append(question)
        return [chunk]

    service.retrieve = fake_retrieve

    results = service.retrieve_multi_query("What causes tooth decay?", "What causes tooth decay?")

    assert len(calls) > 1
    assert any("tooth" in call.lower() or "decay" in call.lower() for call in calls)
    assert results


def test_hyde_retrieval_respects_disabled_flag():
    service = object.__new__(RAGService)
    service.settings = StubRagSettings()
    service.settings.enable_hyde = False
    initial = []
    service.retrieve = lambda question, top_k=None, filters=None: initial
    service.generate_hypothetical_passage = lambda question: (_ for _ in ()).throw(AssertionError("HyDE should not run"))

    assert service.retrieve_hyde("weak query", "weak query") == initial


def test_corrective_retry_runs_multi_query_on_low_confidence():
    service = object.__new__(RAGService)
    service.settings = StubRagSettings()
    retry_chunk = RetrievedChunk(
        text="Dental caries is tooth decay.",
        citation=SourceCitation(document_name="Dental Caries", page_number=1, chunk_index=1),
        metadata={"query_relevance_score": 1.5},
    )
    service.retrieve = lambda question, top_k=None, filters=None: []
    service.retrieve_multi_query = lambda retrieval_question, original_question, top_k=None, filters=None: [retry_chunk]

    assert service.retrieve_corrective("What is tooth decay?", "What is tooth decay?") == [retry_chunk]


def test_adaptive_mode_routes_by_query_type():
    service = object.__new__(RAGService)
    service.settings = StubRagSettings()

    assert service.select_effective_mode("adaptive", "symptom_guidance", "tooth pain", {}) == "corrective"
    assert service.select_effective_mode("adaptive", "roman_urdu", "Roman Urdu me jawab do", {}) == "multi_query"
    assert service.select_effective_mode("adaptive", "document_specific", "question", {"document_id": "doc_1"}) == "corrective"


def test_self_check_flags_ungrounded_and_prescribing_answers():
    service = object.__new__(RAGService)
    chunk = RetrievedChunk(
        text="Dental caries is caused by biofilm and dietary sugars.",
        citation=SourceCitation(document_name="Dental Caries", page_number=1, chunk_index=1),
        metadata={},
    )

    result = service.self_check_answer(
        "What causes tooth pain?",
        "Take 500 mg antibiotic daily for jaw fracture surgery.",
        [chunk],
    )

    assert not result["passed"]
    assert "ungrounded" in result["reasons"]
    assert "prescribing_language" in result["reasons"]


def test_query_classifier_does_not_block_unknown_terms():
    assert classify_query("Who won the football match yesterday?") == "simple_dental_explanation"
    assert classify_query("What causes gum disease?") == "simple_dental_explanation"
    assert classify_query("What is maxillofacial surgery?") == "simple_dental_explanation"


def test_answer_returns_general_fallback_mode_without_sources(monkeypatch):
    service = object.__new__(RAGService)
    service.settings = type(
        "Settings",
        (),
        {
            "rag_mode": "simple",
            "allow_general_fallback": True,
            "enable_memory": False,
            "enable_hyde": False,
            "enable_self_check": False,
            "retrieval_top_k": 5,
            "retrieval_min_relevance_score": 1.1,
        },
    )()
    service.llm = type("LLM", (), {"is_configured": False})()
    service.retrieve_for_mode = lambda question, top_k=None, filters=None: []

    result = service.answer("What causes dental caries?")

    assert result.answer_mode == "general_fallback"
    assert result.sources == []
    assert "service is temporarily unavailable" in result.answer.lower()


def test_general_fallback_returns_patient_facing_answer_without_context_prefix():
    class FakeLLM:
        is_configured = True

        def generate(self, prompt, temperature=0.1, top_p=0.8, system_prompt=""):
            return (
                "Direct Answer:\nDental caries is tooth decay.\n\n"
                "Explanation:\n- Bacteria use sugar to make acid.\n- Acid weakens enamel.\n\n"
                "Safety Note:\nSee a licensed dentist for pain or swelling."
            )

    service = object.__new__(RAGService)
    service.settings = type("Settings", (), {"allow_general_fallback": True})()
    service.llm = FakeLLM()

    answer = service.generate_general_fallback_answer("Explain dental caries in detail.")

    assert answer.startswith("Direct Answer:")
    assert "I could not find enough relevant evidence" not in answer
    assert "uploaded documents" not in answer.lower()


def test_web_fallback_is_patient_facing_and_hides_internal_llm_state():
    answer = web_results_fallback_answer(
        [
            WebSearchResult(
                title="Tooth Decay | NIDCR",
                url="https://www.nidcr.nih.gov/health-info/tooth-decay",
                content=(
                    "Tooth decay begins when bacteria in your mouth make acids that attack the tooth's surface "
                    "(enamel). This can lead to a small hole in a tooth, called a cavity. If tooth decay is not "
                    "treated, it can cause pain, infection, and even tooth loss."
                ),
            ),
            WebSearchResult(
                title="Tooth decay - NHS",
                url="https://www.nhs.uk/conditions/tooth-decay/",
                content="Tooth decay is often caused by having too much sugary food and drink and not cleaning your teeth and gums regularly.",
            ),
        ]
    )

    assert "Tooth decay" in answer
    assert "bacteria" in answer.lower()
    assert "configured llm" not in answer.lower()
    assert "trusted web sources found" not in answer.lower()
    assert "Sources" not in answer


def test_repair_patient_facing_answer_replaces_template_leak_for_caries():
    leaked = (
        'Direct Answer: [answer]"\n\n'
        '2. Then "Explanation:" followed by a list of 4 points\n'
        "We are to explain dental caries in detail.\n"
        "Key points to cover (4 points):"
    )

    repaired = repair_patient_facing_answer("explain dental caries in detail?", leaked)

    assert repaired == "I do not have enough relevant evidence in the uploaded documents."
    assert "[answer]" not in repaired
    assert "We are to explain" not in repaired


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


def test_text_model_failure_returns_controlled_unavailable_answer():
    class FailingLLM:
        is_configured = True

        def generate(self, *args, **kwargs):
            raise LLMGenerationError("model down")

    service = object.__new__(RAGService)
    service.llm = FailingLLM()
    chunks = [
        RetrievedChunk(
            text="Oral and maxillofacial injuries can involve the oral cavity, teeth, jaws, and surrounding soft tissues.",
            citation=SourceCitation(document_name="Oral Surgery", page_number=10, chunk_index=1),
            metadata={"trust_level": "high", "review_status": "approved", "quality_score": 0.9},
        )
    ]

    answer = service.generate_answer("Oral and maxillofacial injuries oral cavity", chunks)

    assert "service is temporarily unavailable" in answer.lower()


def test_text_only_rag_does_not_call_vision_model():
    class FakeLLM:
        is_configured = True

        def generate(self, prompt, **kwargs):
            assert "No relevant visual observations." in prompt
            return "Direct Answer: Orthodontics is a dental specialty."

        def analyze_image(self, *args, **kwargs):
            raise AssertionError("vision should not run")

    service = object.__new__(RAGService)
    service.settings = StubRagSettings()
    service.llm = FakeLLM()
    chunk = RetrievedChunk(
        text="Orthodontics is a dental specialty related to diagnosis and correction of malocclusion.",
        citation=SourceCitation(document_name="Orthodontics", page_number=1, chunk_index=1),
        metadata={"trust_level": "high", "review_status": "approved", "quality_score": 0.9},
    )
    service.retrieve_for_mode = lambda question, top_k=None, filters=None: [chunk]
    service.retrieve_visuals = lambda question, chunks, filters=None: []

    result = service.answer("What is orthodontics?")

    assert result.answer_mode == "rag_grounded"
    assert result.visuals == []
    assert "Orthodontics" in result.answer


def test_visual_question_passes_observation_to_text_model_and_returns_visual_card():
    captured = {}

    class FakeLLM:
        is_configured = True

        def analyze_image(self, image_path, prompt, **kwargs):
            captured["image_path"] = image_path
            assert "VISUAL_NOT_RELEVANT" in prompt
            return "The diagram shows brackets connected by an orthodontic archwire."

        def generate(self, prompt, **kwargs):
            captured["prompt"] = prompt
            return "Direct Answer: The retrieved diagram shows brackets connected by an archwire."

    service = object.__new__(RAGService)
    service.settings = StubRagSettings()
    service.llm = FakeLLM()
    chunk = RetrievedChunk(
        text="Fixed orthodontic appliances include brackets and archwires.",
        citation=SourceCitation(document_name="Orthodontics", document_id="doc1", page_number=5, chunk_index=2),
        metadata={"trust_level": "high", "review_status": "approved", "quality_score": 0.9, "chunk_id": "c1"},
    )
    visual = RetrievedVisual(
        citation=VisualCitation(
            visual_id="v1",
            document_id="doc1",
            document_name="Orthodontics",
            page_number=5,
            visual_type="diagram",
            image_path="uploads/extracted_visuals/doc1/figure.png",
            image_url="/uploads/extracted_visuals/doc1/figure.png",
            caption_text="Figure: fixed orthodontic appliance.",
        ),
        metadata={"quality_score": 0.9, "related_chunk_ids": ["c1"]},
        rerank_score=1.4,
    )
    service.retrieve_for_mode = lambda question, top_k=None, filters=None: [chunk]
    service.retrieve_visuals = lambda question, chunks, filters=None: [visual]

    result = service.answer("What does the orthodontic diagram show?")

    assert "brackets connected by an orthodontic archwire" in captured["prompt"]
    assert result.visuals and result.visuals[0].visual_id == "v1"


def test_irrelevant_visual_is_not_returned_with_answer():
    class FakeLLM:
        is_configured = True

        def analyze_image(self, *args, **kwargs):
            return "VISUAL_NOT_RELEVANT"

        def generate(self, prompt, **kwargs):
            return "Direct Answer: The text evidence describes enamel demineralization."

    service = object.__new__(RAGService)
    service.settings = StubRagSettings()
    service.llm = FakeLLM()
    chunk = RetrievedChunk(
        text="Dental caries involves enamel demineralization.",
        citation=SourceCitation(document_name="Caries", document_id="doc1", page_number=1, chunk_index=1),
        metadata={"trust_level": "high", "review_status": "approved", "quality_score": 0.9},
    )
    visual = RetrievedVisual(
        citation=VisualCitation(
            visual_id="v2",
            document_id="doc1",
            document_name="Caries",
            page_number=10,
            visual_type="figure",
            image_path="uploads/extracted_visuals/doc1/unrelated.png",
            image_url="/uploads/extracted_visuals/doc1/unrelated.png",
        ),
        metadata={"quality_score": 0.9},
        rerank_score=1.4,
    )
    service.retrieve_for_mode = lambda question, top_k=None, filters=None: [chunk]
    service.retrieve_visuals = lambda question, chunks, filters=None: [visual]

    result = service.answer("Show a figure for tooth decay.")

    assert result.visuals == []
    assert "enamel demineralization" in result.answer


def test_vision_model_failure_continues_with_text_only_rag():
    class FakeLLM:
        is_configured = True

        def analyze_image(self, *args, **kwargs):
            raise LLMGenerationError("vision down")

        def generate(self, prompt, **kwargs):
            return "Direct Answer: The table evidence describes periodontal measurements."

    service = object.__new__(RAGService)
    service.settings = StubRagSettings()
    service.llm = FakeLLM()
    chunk = RetrievedChunk(
        text="The periodontal table summarizes probing depth measurements.",
        citation=SourceCitation(document_name="Periodontology", document_id="doc1", page_number=7, chunk_index=3),
        metadata={"trust_level": "high", "review_status": "approved", "quality_score": 0.9},
    )
    visual = RetrievedVisual(
        citation=VisualCitation(
            visual_id="v3",
            document_id="doc1",
            document_name="Periodontology",
            page_number=7,
            visual_type="table",
            image_path="uploads/extracted_visuals/doc1/table.png",
            image_url="/uploads/extracted_visuals/doc1/table.png",
        ),
        metadata={"quality_score": 0.9},
        rerank_score=1.5,
    )
    service.retrieve_for_mode = lambda question, top_k=None, filters=None: [chunk]
    service.retrieve_visuals = lambda question, chunks, filters=None: [visual]

    result = service.answer("Which table is relevant to periodontal measurements?")

    assert result.answer_mode == "rag_grounded"
    assert result.visuals == []
    assert "periodontal measurements" in result.answer
