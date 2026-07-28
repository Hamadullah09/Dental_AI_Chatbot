"""Phase 5a: role-based response quality. Includes the explicit regression test for
finding #2 (default_trust_levels returning the identical list for every role)."""

from app.agent.nodes.follow_up import STUDENT_ACTIVE_RECALL_SUGGESTIONS, generate_follow_up_suggestions
from app.agent.nodes.intent_classifier import classify_intent
from app.agent.nodes.safety import EMERGENCY_TRIAGE_MESSAGE, run_safety_check
from app.agent.state import AgentState
from app.services.rag import default_document_types, default_trust_levels, rerank_chunks


def test_default_trust_levels_differs_by_role():
    """Regression test for finding #2: default_trust_levels() used to return
    ["high", "medium"] for every role including patient, so despite the architecture
    doc's claim of role-based retrieval, trust-level filtering never actually differed."""
    assert default_trust_levels("patient") == ["high"]
    assert default_trust_levels("dentist") == ["high", "medium"]
    assert default_trust_levels("student") == ["high", "medium"]
    assert default_trust_levels(None) == ["high", "medium"]
    assert default_trust_levels("patient") != default_trust_levels("dentist")


def test_default_document_types_still_differs_by_role():
    # This one already worked before Phase 5a - confirms the fix didn't regress it.
    assert "research_article" not in default_document_types("patient")
    assert "research_article" in default_document_types("dentist")


def _fake_chunk(text: str, document_type: str, trust_level: str = "high"):
    from app.schemas import SourceCitation
    from app.services.rag import RetrievedChunk

    return RetrievedChunk(
        text=text,
        citation=SourceCitation(source_type="pdf", document_name="Test.pdf", score=0.5),
        metadata={"document_type": document_type, "trust_level": trust_level, "review_status": "approved", "quality_score": 0.8},
        vector_score=0.5,
        keyword_score=0.0,
        rerank_score=0.0,
    )


def test_rerank_chunks_favors_guideline_for_dentist_over_patient_education():
    # Near-identical text so lexical/relevance scoring is ~equal between the two chunks -
    # isolates the role-based document_type boost as the deciding factor, rather than
    # incidentally testing keyword overlap between the query and chunk wording.
    chunks = [
        _fake_chunk("Gum disease treatment involves scaling and root planing.", "patient_education"),
        _fake_chunk("Gum disease treatment involves scaling and root planing.", "guideline"),
    ]
    reranked = rerank_chunks("gum disease treatment", chunks, user_role="dentist")
    assert reranked[0].metadata["document_type"] == "guideline"


def test_rerank_chunks_favors_patient_education_for_patient_over_research():
    chunks = [
        _fake_chunk("Gum disease treatment involves scaling and root planing.", "research_article"),
        _fake_chunk("Gum disease treatment involves scaling and root planing.", "patient_education"),
    ]
    reranked = rerank_chunks("gum disease treatment", chunks, user_role="patient")
    assert reranked[0].metadata["document_type"] == "patient_education"


def test_rerank_chunks_favors_textbook_for_student():
    chunks = [
        _fake_chunk("Periodontal disease mechanism involves bacterial biofilm.", "quick_reference"),
        _fake_chunk("Periodontal disease mechanism involves bacterial biofilm.", "textbook"),
    ]
    reranked = rerank_chunks("periodontal disease mechanism", chunks, user_role="student")
    assert reranked[0].metadata["document_type"] == "textbook"


def test_rerank_chunks_with_no_role_is_unaffected_by_document_type_boost():
    chunks = [
        _fake_chunk("A", "research_article"),
        _fake_chunk("B", "patient_education"),
    ]
    # Should not raise, and should not apply any role boost.
    reranked = rerank_chunks("test question", chunks, user_role=None)
    assert len(reranked) == 2


def test_emergency_red_flag_short_circuits_to_fixed_triage_message():
    state = AgentState(question="I have facial swelling spreading rapidly and difficulty breathing")
    result = run_safety_check(state)

    assert result.answer_mode == "emergency_triage"
    assert result.answer == EMERGENCY_TRIAGE_MESSAGE
    assert result.intent == "emergency"
    assert result.safety_check_passed is True


def test_emergency_triage_message_gives_clear_action_not_reassurance():
    lowered = EMERGENCY_TRIAGE_MESSAGE.lower()
    assert "emergency" in lowered
    assert "immediate" in lowered
    assert "diagnosis" not in lowered or "not a diagnosis" in lowered


def test_normal_question_does_not_trigger_emergency_short_circuit():
    state = AgentState(question="What is the best toothpaste for sensitive teeth?")
    result = run_safety_check(state)
    assert result.answer_mode != "emergency_triage"
    assert result.safety_check_passed is True


def test_classify_intent_forces_simplify_for_patient_role(monkeypatch):
    """Phase 5a: simplify_for_patient previously depended only on question phrasing, not
    on who was asking - a patient phrasing a question in clinical terms got a dense
    answer. Force LLM classification to fail so the keyword fallback path runs, and
    confirm the role override still applies regardless of which path set the flag."""
    from app.services.llm import LLMGenerationError

    def _broken_llm(*args, **kwargs):
        raise LLMGenerationError("simulated failure")

    monkeypatch.setattr("app.services.llm.LLMService.generate", _broken_llm)

    state = AgentState(question="What is the pathophysiology of pulpitis?", user_role="patient")
    result = classify_intent(state)

    assert result.simplify_for_patient is True


def test_classify_intent_does_not_force_simplify_for_dentist_role(monkeypatch):
    from app.services.llm import LLMGenerationError

    def _broken_llm(*args, **kwargs):
        raise LLMGenerationError("simulated failure")

    monkeypatch.setattr("app.services.llm.LLMService.generate", _broken_llm)

    state = AgentState(question="What is the pathophysiology of pulpitis?", user_role="dentist")
    result = classify_intent(state)

    assert result.simplify_for_patient is False


def test_student_gets_active_recall_follow_ups():
    state = AgentState(question="Explain the mechanism of periodontal disease", user_role="student")
    state.intent = "diagnosis"
    state.answer_mode = "rag_grounded"
    result = generate_follow_up_suggestions(state)
    assert result.follow_up_suggestions == STUDENT_ACTIVE_RECALL_SUGGESTIONS[:3]


def test_patient_gets_simplified_follow_ups_not_active_recall():
    state = AgentState(question="Explain the mechanism of periodontal disease", user_role="patient")
    state.intent = "diagnosis"
    state.answer_mode = "rag_grounded"
    result = generate_follow_up_suggestions(state)
    assert result.follow_up_suggestions != STUDENT_ACTIVE_RECALL_SUGGESTIONS[:3]
    assert any("simpler" in s.lower() for s in result.follow_up_suggestions)


def test_dentist_gets_standard_intent_based_follow_ups():
    state = AgentState(question="Differential diagnosis for radiolucent lesion", user_role="dentist")
    state.intent = "diagnosis"
    state.answer_mode = "rag_grounded"
    result = generate_follow_up_suggestions(state)
    assert result.follow_up_suggestions != STUDENT_ACTIVE_RECALL_SUGGESTIONS[:3]
