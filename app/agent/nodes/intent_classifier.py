from __future__ import annotations

import json
import time
from typing import Any

from app.agent.state import AgentState
from app.core.logging import get_logger

logger = get_logger(__name__)

INTENT_DEFINITIONS = {
    "general": "General conversation, greetings, or questions not specifically about dental health",
    "symptom": "Questions about dental symptoms like pain, swelling, bleeding, sensitivity",
    "treatment": "Questions about dental procedures, treatments, surgeries, or therapies",
    "diagnosis": "Questions about diagnosing dental conditions or interpreting findings",
    "patient_education": "Requests for simple explanations of dental concepts in layman's terms",
    "clinical_decision": "Questions requiring differential diagnosis, treatment planning, or clinical guidelines for dental professionals",
    "research": "Literature search, evidence hierarchy, paper summarization, guideline comparison",
    "image_analysis": "Questions about interpreting X-rays, radiographs, CBCT scans, or clinical photographs",
    "prescription_explain": "Questions about explaining or understanding prescriptions, medications, dosages",
    "report_explain": "Questions about explaining dental reports, lab results, or referral letters",
    "emergency": "Urgent dental situations requiring immediate professional attention",
    "conversational": "Greetings, thanks, small talk, or non-medical conversation",
}

SUB_INTENT_MAP: dict[str, list[str]] = {
    "symptom": ["pain", "swelling", "bleeding", "sensitivity", "infection", "trauma"],
    "treatment": ["surgical", "restorative", "orthodontic", "preventive", "cosmetic"],
    "diagnosis": ["caries", "periodontal", "endodontic", "oral_pathology", "temporomandibular"],
    "patient_education": ["procedure_explain", "condition_explain", "prevention", "hygiene"],
    "clinical_decision": ["differential", "treatment_planning", "guidelines", "contraindications", "material_selection"],
    "research": ["literature_search", "paper_summary", "guideline_comparison", "evidence_level"],
    "image_analysis": ["xray", "cbct", "photograph", "diagram", "chart"],
}

EMERGENCY_PATTERNS = [
    "knocked.out", "avuls", "severe pain", "uncontrollable bleeding",
    "facial swelling", "difficulty breathing", "swollen eye", "trauma",
    "fractur", "broken tooth", "abscess", " cellulitis", "trismus",
    "lockjaw", "cannot open", "swallowing difficulty",
]

SAFETY_RED_FLAGS = [
    "how to extract", "self.extract", "pull my own tooth",
    "bypass", "ignore", "unauthorized", "jailbreak",
    "ignore previous instructions", "ignore all rules",
]

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous\s+)?instructions",
    r"forget\s+(all\s+)?(previous\s+)?(rules|instructions|prompts)",
    r"you\s+are\s+now\s+",
    r"act\s+as\s+",
    r"system\s+prompt",
    r"override\s+",
    r"new\s+role\s*:",
    r"you\s+must\s+ignore",
    r"disregard\s+(all\s+)?",
]


def _check_emergency_keywords(question_lower: str) -> bool:
    return any(p in question_lower for p in EMERGENCY_PATTERNS)


def _check_safety_flags(question_lower: str) -> list[str]:
    flags = []
    import re
    for pattern in SAFETY_RED_FLAGS:
        if pattern in question_lower:
            flags.append(f"unsafe_request:{pattern}")
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, question_lower, re.IGNORECASE):
            flags.append(f"prompt_injection:{pattern}")
            break
    return flags


def classify_intent(state: AgentState) -> AgentState:
    start = time.perf_counter()
    question_lower = state.question.lower()

    state.safety_flags = _check_safety_flags(question_lower)

    if _check_emergency_keywords(question_lower):
        state.intent = "emergency"
        state.intent_confidence = 1.0
        state.explainability_notes.append("Emergency keywords detected in query")
        duration_ms = (time.perf_counter() - start) * 1000
        state.add_trace("intent_classifier", "completed", f"Emergency intent (keyword)", duration_ms)
        return state

    if state.safety_flags:
        state.safety_check_passed = False
        state.intent = "general"
        state.intent_confidence = 1.0
        state.answer = (
            "I cannot process this request. Please ask a appropriate dental health question. "
            "If you have a genuine dental concern, please describe it and I'll be happy to help."
        )
        state.answer_mode = "safety_blocked"
        state.add_trace("intent_classifier", "safety_blocked", f"Flags: {state.safety_flags}")
        return state

    try:
        from app.services.llm import LLMService
        llm = LLMService()

        intent_descriptions = "\n".join(
            f"- {k}: {v}" for k, v in sorted(INTENT_DEFINITIONS.items())
        )

        system_prompt = (
            "You are an intent classifier for a dental AI chatbot. "
            "Analyze the user's question and return a JSON object with:\n"
            "- intent: one of the intent types listed below\n"
            "- sub_intent: a more specific subtype from the list below\n"
            "- confidence: float 0-1\n"
            "- entities: object with keys like 'symptoms', 'treatments', 'conditions', 'procedures', 'anatomy' - each a list of strings\n"
            "- simplify_for_patient: boolean, true if user asks for simple/easy/layman explanation\n\n"
            f"Intent types:\n{intent_descriptions}\n\n"
            "Respond ONLY with valid JSON, no other text."
        )

        result = llm.generate(
            state.question,
            system_prompt=system_prompt,
            temperature=0.1,
        )

        start_idx = result.find("{")
        end_idx = result.rfind("}") + 1
        if start_idx >= 0 and end_idx > start_idx:
            parsed = json.loads(result[start_idx:end_idx])
            state.intent = parsed.get("intent", "general")
            state.sub_intent = parsed.get("sub_intent", "")
            state.intent_confidence = float(parsed.get("confidence", 0.5))
            state.detected_entities = parsed.get("entities", {})
            state.simplify_for_patient = bool(parsed.get("simplify_for_patient", False))

            if state.intent not in INTENT_DEFINITIONS:
                state.intent = "general"

            if state.simplify_for_patient and state.intent not in ("patient_education", "conversational"):
                state.explainability_notes.append("User requested simplified explanation")

    except Exception as exc:
        logger.debug(f"LLM intent classification failed, using keyword fallback: {exc}")
        _keyword_intent_fallback(state, question_lower)

    duration_ms = (time.perf_counter() - start) * 1000
    state.add_trace("intent_classifier", "completed", f"Intent: {state.intent} (confidence: {state.intent_confidence:.2f})", duration_ms)
    return state


def _keyword_intent_fallback(state: AgentState, question_lower: str) -> None:
    from app.agent.nodes.planner import (
        SYMPTOM_KEYWORDS, TREATMENT_KEYWORDS, EMERGENCY_KEYWORDS,
        VISUAL_KEYWORDS, DIRECT_ANSWER_KEYWORDS, _contains_keyword,
    )

    if any(word in question_lower for word in EMERGENCY_KEYWORDS):
        state.intent = "emergency"
    elif any(word in question_lower for word in VISUAL_KEYWORDS):
        state.intent = "image_analysis"
    elif any(word in question_lower for word in TREATMENT_KEYWORDS):
        state.intent = "treatment"
    elif any(word in question_lower for word in SYMPTOM_KEYWORDS):
        state.intent = "symptom"
    elif any(word in question_lower for word in ["research", "study", "literature", "evidence", "paper", "journal"]):
        state.intent = "research"
    elif any(word in question_lower for word in ["prescription", "medication", "dosage", "drug"]):
        state.intent = "prescription_explain"
    elif any(word in question_lower for word in ["report", "lab", "result", "referral"]):
        state.intent = "report_explain"
    elif any(word in question_lower for word in ["differential", "treatment plan", "guideline", "contraindication", "material"]):
        state.intent = "clinical_decision"
    elif any(word in question_lower for word in ["simple", "layman", "easy", "explain like", "basic"]):
        state.intent = "patient_education"
        state.simplify_for_patient = True
    elif any(_contains_keyword(question_lower, phrase) for phrase in DIRECT_ANSWER_KEYWORDS):
        state.intent = "conversational"
    else:
        state.intent = "general"

    state.intent_confidence = 0.6
