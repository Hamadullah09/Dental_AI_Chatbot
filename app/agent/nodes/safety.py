from __future__ import annotations

import re
import time
from typing import Any

from app.agent.state import AgentState
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

MEDICAL_EMERGENCY_PATTERNS = [
    r"(difficulty|trouble)\s+(breathing|swallowing)",
    r"facial\s+swelling\s+(spreading|rapid)",
    r"uncontrollable\s+bleeding",
    r"swollen\s+eye",
    r"cellulitis",
    r"trismus|lockjaw",
    r"severe\s+(pain|trauma)",
    r"(knocked|avuls)\s+out",
    r"abscess\s+(with|and)\s+fever",
]

UNSAFE_ADVICE_PATTERNS = [
    r"how\s+(to|can\s+I)\s+(extract|remove|pull)\s+(my\s+)?(own\s+)?tooth",
    r"self[\s-]?(extract|medicate|diagnose|surgery)",
    r"home\s+remedy\s+(for|to)\s+(treat|cure)\s+(cavity|abscess|infection)",
    r"can\s+I\s+(ignore|skip|avoid)\s+(treatment|filling|root.canal|extraction)",
    r"how\s+to\s+(make|prepare|mix)\s+(dental|tooth)\s+(filling|cement|material)\s+at\s+home",
    r"how\s+to\s+(prescribe|recommend)\s+(antibiotics|medication|drug)\s+for",
    r"what\s+dosage\s+of\s+\w+\s+(for|should)",
]

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous\s+)?(instructions|rules|prompts|directives)",
    r"forget\s+(all\s+)?(previous\s+)?(context|rules|instructions)",
    r"you\s+are\s+now\s+a?\s*(doctor|dentist|surgeon|hacker|assistant)\s+without",
    r"act\s+as\s+(if\s+you\s+are|though\s+you\s+are)\s+",
    r"override\s+(your\s+)?(system|safety|guidelines|protocol)",
    r"disregard\s+(your\s+)?(protocol|guidelines|rules|safety)",
    r"new\s+role\s*:\s*",
    r"((system|main)\s+)?prompt\s*:",
    r"you\s+must\s+(now\s+)?ignore\s+",
    r"no\s+(ethical|moral|safety|medical)\s+(guidelines|restrictions|boundaries|limits)",
]

DRUG_MISUSE_PATTERNS = [
    r"how\s+to\s+(overdose|abuse|misuse)\s+",
    r"get\s+high\s+(on|from|with)",
    r"(sale|buy|purchase)\s+(without\s+)?prescription",
    r"(fake|forged|falsify)\s+prescription",
]


def _check_emergency(question_lower: str) -> list[str]:
    flags = []
    for pattern in MEDICAL_EMERGENCY_PATTERNS:
        if re.search(pattern, question_lower, re.IGNORECASE):
            flags.append(f"medical_emergency:{pattern}")
    return flags


def _check_unsafe_advice(question_lower: str) -> list[str]:
    flags = []
    for pattern in UNSAFE_ADVICE_PATTERNS:
        if re.search(pattern, question_lower, re.IGNORECASE):
            flags.append(f"unsafe_advice:{pattern}")
    return flags


def _check_drug_misuse(question_lower: str) -> list[str]:
    flags = []
    for pattern in DRUG_MISUSE_PATTERNS:
        if re.search(pattern, question_lower, re.IGNORECASE):
            flags.append(f"drug_misuse:{pattern}")
    return flags


def _check_prompt_injection(question_lower: str) -> list[str]:
    flags = []
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, question_lower, re.IGNORECASE):
            flags.append(f"prompt_injection:{pattern}")
            break
    return flags


def run_safety_check(state: AgentState) -> AgentState:
    start = time.perf_counter()
    question_lower = state.question.lower()

    all_flags = []
    all_flags.extend(_check_emergency(question_lower))
    all_flags.extend(_check_unsafe_advice(question_lower))
    all_flags.extend(_check_drug_misuse(question_lower))
    all_flags.extend(_check_prompt_injection(question_lower))

    state.safety_flags = all_flags

    if any(f.startswith("medical_emergency") for f in all_flags):
        state.intent = "emergency"
        state.safety_check_passed = True
        state.explainability_notes.append("Emergency situation detected - prioritizing urgent response")
        state.add_trace("safety_checker", "emergency", "Medical emergency detected")
    elif all_flags:
        state.safety_check_passed = False
        blocked_types = set(f.split(":")[0] for f in all_flags)
        state.add_trace("safety_checker", "blocked", f"Safety flags: {', '.join(blocked_types)}")

        if any(f.startswith("prompt_injection") for f in all_flags):
            state.answer = "I cannot process this request. Please ask a dental health question."
            state.answer_mode = "safety_blocked"
        elif any(f.startswith("drug_misuse") for f in all_flags):
            state.answer = "I cannot provide information about drug misuse or abuse. Please consult a healthcare professional for proper medical guidance."
            state.answer_mode = "safety_blocked"
        elif any(f.startswith("unsafe_advice") for f in all_flags):
            state.answer = (
                "I cannot provide instructions for self-treatment or self-diagnosis that could be harmful. "
                "Please consult a licensed dentist for proper evaluation and care."
            )
            state.answer_mode = "safety_blocked"
    else:
        state.safety_check_passed = True

    duration_ms = (time.perf_counter() - start) * 1000
    if all_flags:
        state.add_trace("safety_checker", "completed", f"{len(all_flags)} flag(s)", duration_ms)
    return state
