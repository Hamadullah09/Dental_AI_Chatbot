from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.schemas import SourceCitation, VisualCitation


@dataclass
class AgentState:
    question: str
    session_id: str | None = None
    user_id: str | None = None
    user_role: str = "patient"
    document_id: str | None = None
    search_web: bool = False
    top_k: int | None = None
    filters: dict[str, Any] = field(default_factory=dict)
    conversation_history: list[dict[str, str]] = field(default_factory=list)

    intent: str = "general"
    query_variants: list[str] = field(default_factory=list)
    rewritten_query: str = ""

    retrieved_chunks: list[dict[str, Any]] = field(default_factory=list)
    retrieved_visuals: list[dict[str, Any]] = field(default_factory=list)
    reranked_chunks: list[dict[str, Any]] = field(default_factory=list)
    reranked_visuals: list[dict[str, Any]] = field(default_factory=list)

    context_text: str = ""
    visual_context: str = ""
    memory_context: str = ""

    answer: str = ""
    sources: list[SourceCitation] = field(default_factory=list)
    visuals: list[VisualCitation] = field(default_factory=list)
    answer_mode: str = "rag_grounded"
    disclaimer: str = ""

    error: str | None = None
    retry_count: int = 0
    max_retries: int = 2

    trace_log: list[dict[str, Any]] = field(default_factory=list)

    def add_trace(self, node: str, status: str, detail: str = "", duration_ms: float = 0) -> None:
        self.trace_log.append({
            "node": node,
            "status": status,
            "detail": detail,
            "duration_ms": duration_ms,
        })
