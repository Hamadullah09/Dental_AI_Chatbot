from __future__ import annotations

import time

from app.agent.state import AgentState
from app.core.logging import get_logger

logger = get_logger(__name__)

SUGGESTION_MAP: dict[str, list[str]] = {
    "symptom": [
        "Would you like to know the treatment options for this condition?",
        "Should I explain when you should see a dentist?",
        "Want to learn about prevention tips?",
    ],
    "treatment": [
        "Would you like to know the recovery time for this procedure?",
        "Should I explain the risks and complications?",
        "Want to compare this with alternative treatments?",
    ],
    "diagnosis": [
        "Would you like to know the treatment options?",
        "Should I explain the diagnostic criteria in more detail?",
        "Want to understand how this condition progresses?",
    ],
    "patient_education": [
        "Would you like a more detailed explanation?",
        "Should I explain related dental anatomy?",
        "Want to know how to prevent this condition?",
    ],
    "clinical_decision": [
        "Would you like to compare treatment guidelines?",
        "Should I explain contraindications in more detail?",
        "Want to review the evidence level for this recommendation?",
    ],
    "research": [
        "Would you like a more detailed paper summary?",
        "Should I compare this with other studies?",
        "Want to explore the evidence hierarchy?",
    ],
    "image_analysis": [
        "Would you like me to explain another finding in this image?",
        "Should I discuss clinical implications?",
        "Want to know what to look for in normal vs. abnormal cases?",
    ],
    "prescription_explain": [
        "Would you like to know about potential side effects?",
        "Should I explain drug interactions?",
        "Want to understand how this medication works?",
    ],
    "report_explain": [
        "Would you like me to explain specific values in this report?",
        "Should I discuss what the next steps are?",
        "Want to understand the normal ranges?",
    ],
    "general": [
        "Would you like to know more about dental health?",
        "Should I explain when to visit a dentist?",
        "Want to learn about preventive dental care?",
    ],
}


def generate_follow_up_suggestions(state: AgentState) -> AgentState:
    start = time.perf_counter()

    if state.answer_mode in ("safety_blocked", "error", "insufficient_evidence"):
        state.follow_up_suggestions = []
        state.add_trace("follow_up_generator", "skipped", f"Mode: {state.answer_mode}")
        return state

    suggestions = list(SUGGESTION_MAP.get(state.intent, SUGGESTION_MAP["general"]))

    if state.simplify_for_patient:
        suggestions = [
            "Would you like me to explain this in even simpler terms?",
            "Should I break down the key points for you?",
            "Want to learn about related dental care tips?",
        ]

    state.follow_up_suggestions = suggestions[:3]

    duration_ms = (time.perf_counter() - start) * 1000
    state.add_trace("follow_up_generator", "completed", f"{len(suggestions)} suggestion(s)", duration_ms)
    return state
