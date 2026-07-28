"""Phase 5a: a small labeled persona eval set, run in CI (via pytest) rather than a
separate script, since every property checked here is derivable without a live LLM call -
the same properties an LLM-based eval would need a judge model to verify are instead
asserted directly against the deterministic role-shaping functions. This is what stops a
change to one persona's prompt/retrieval shaping from silently regressing another's: each
case below pins down a concrete, role-specific expectation.

If you add a new persona-facing feature (e.g. a new retrieval boost, a new prompt
clause), add a case here rather than only testing it in isolation elsewhere - the point
of this file is that it's one place that has to keep passing for all three personas at
once.
"""

import pytest

from app.services.rag import (
    contains_prescribing_language,
    default_document_types,
    default_trust_levels,
    role_behavior_instruction,
)

PERSONA_CASES = [
    {
        "role": "patient",
        "question": "What is a cavity and how is it treated?",
        "expect_trust_levels": ["high"],
        "expect_document_types_exclude": ["research_article"],
        "expect_prescribing_language_redirected": True,
        "expect_prompt_contains_any": ["simple", "reassuring"],
        "expect_prompt_not_contains": ["differential"],
    },
    {
        "role": "dentist",
        "question": "What is the differential diagnosis for a radiolucent periapical lesion?",
        "expect_trust_levels": ["high", "medium"],
        "expect_document_types_exclude": [],
        "expect_prescribing_language_redirected": False,
        "expect_prompt_contains_any": ["differential", "clinical"],
        "expect_prompt_not_contains": ["simple, reassuring"],
    },
    {
        "role": "student",
        "question": "Explain the mechanism of pulpitis progression.",
        "expect_trust_levels": ["high", "medium"],
        "expect_document_types_exclude": [],
        "expect_prescribing_language_redirected": True,
        "expect_prompt_contains_any": ["educational", "concept-based", "exam-friendly"],
        "expect_prompt_not_contains": ["differential"],
    },
]


@pytest.mark.parametrize("case", PERSONA_CASES, ids=[c["role"] for c in PERSONA_CASES])
def test_persona_trust_levels(case):
    assert default_trust_levels(case["role"]) == case["expect_trust_levels"]


@pytest.mark.parametrize("case", PERSONA_CASES, ids=[c["role"] for c in PERSONA_CASES])
def test_persona_document_type_exclusions(case):
    doc_types = default_document_types(case["role"])
    for excluded in case["expect_document_types_exclude"]:
        assert excluded not in doc_types, f"{case['role']} should not receive {excluded} by default"


@pytest.mark.parametrize("case", PERSONA_CASES, ids=[c["role"] for c in PERSONA_CASES])
def test_persona_prescribing_language_policy(case):
    sample_answer = "Take 500mg amoxicillin tablet twice daily for 7 days."
    flagged = contains_prescribing_language(sample_answer, user_role=case["role"])
    assert flagged is case["expect_prescribing_language_redirected"]


@pytest.mark.parametrize("case", PERSONA_CASES, ids=[c["role"] for c in PERSONA_CASES])
def test_persona_prompt_shaping(case):
    instruction = role_behavior_instruction(case["role"]).lower()
    assert any(term in instruction for term in case["expect_prompt_contains_any"]), (
        f"{case['role']} instruction missing expected persona language: {instruction}"
    )
    for forbidden in case["expect_prompt_not_contains"]:
        assert forbidden not in instruction, (
            f"{case['role']} instruction unexpectedly contains another persona's language: {forbidden!r}"
        )


def test_all_three_personas_produce_distinct_prompt_instructions():
    """Guards against a regression where two personas' prompts collapse to the same
    text (e.g. a bad refactor of role_behavior_instruction's if/elif chain)."""
    instructions = {case["role"]: role_behavior_instruction(case["role"]) for case in PERSONA_CASES}
    assert len(set(instructions.values())) == 3
