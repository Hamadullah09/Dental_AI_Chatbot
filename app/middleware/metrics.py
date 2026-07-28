from __future__ import annotations

import time
from typing import Any

from fastapi import Request
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from app.core.config import get_settings

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

LLM_LATENCY = Histogram(
    "llm_generation_duration_seconds",
    "LLM generation latency in seconds",
    ["provider", "model"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

RETRIEVAL_LATENCY = Histogram(
    "retrieval_duration_seconds",
    "RAG retrieval latency in seconds",
    ["mode"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

RERANK_LATENCY = Histogram(
    "rerank_duration_seconds",
    "Reranking latency in seconds",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
)

CHAT_QUERIES = Counter(
    "chat_queries_total",
    "Total chat queries processed",
    ["answer_mode"],
)

ACTIVE_INGESTIONS = Gauge(
    "active_ingestions",
    "Number of documents currently being ingested",
)

DOCUMENTS_TOTAL = Counter(
    "documents_total",
    "Total documents processed",
    ["status"],
)

EMBEDDING_LATENCY = Histogram(
    "embedding_duration_seconds",
    "Embedding generation latency in seconds",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

USER_SESSIONS = Counter(
    "user_sessions_total",
    "Total user sessions",
)

# --- Reliability (Phase 1) ---

AGENT_GRAPH_FALLBACK_TOTAL = Counter(
    "agent_graph_fallback_total",
    "Times the LangGraph agent path failed and the request fell back to the legacy RAGService path",
    ["reason"],
)

CIRCUIT_BREAKER_STATE = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state per dependency (0=closed, 1=half_open, 2=open)",
    ["name"],
)

CIRCUIT_BREAKER_REJECTIONS = Counter(
    "circuit_breaker_rejections_total",
    "Requests rejected because a circuit breaker was open (fast-failed instead of calling the dependency)",
    ["name"],
)

GATE_QUEUE_DEPTH = Gauge(
    "concurrency_gate_queue_depth",
    "Number of requests currently waiting to acquire a bounded resource (e.g. Ollama GPU slot)",
    ["name"],
)

GATE_ACTIVE = Gauge(
    "concurrency_gate_active",
    "Number of requests currently holding a bounded resource slot",
    ["name"],
)

GATE_WAIT_DURATION = Histogram(
    "concurrency_gate_wait_duration_seconds",
    "Time spent waiting to acquire a bounded resource slot",
    ["name"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0],
)

SERVICE_BUSY_TOTAL = Counter(
    "service_busy_total",
    "Requests rejected because a concurrency gate's wait budget was exhausted",
    ["name"],
)

RETRIEVAL_DEGRADATION_TOTAL = Counter(
    "retrieval_degradation_total",
    "Retrieval tier actually served, when the requested tier was unavailable",
    ["tier"],
)

UPLOAD_IDEMPOTENT_REPLAY_TOTAL = Counter(
    "upload_idempotent_replay_total",
    "Upload requests short-circuited because an Idempotency-Key was already seen",
)

# --- Observability / quality (Phase 3, Phase 5) ---

CITATION_VERIFICATION_TOTAL = Counter(
    "citation_verification_total",
    "Citation verifier outcomes per answer",
    ["result"],
)

RETRIEVAL_HIT_TOTAL = Counter(
    "retrieval_hit_total",
    "Whether a retrieval call returned at least one chunk above the relevance floor",
    ["hit"],
)

TOKEN_USAGE_TOTAL = Counter(
    "token_usage_estimated_total",
    "Estimated token usage per turn (approximate: chars/4), by role and direction",
    ["user_role", "direction"],
)

PERSONA_RESPONSE_TOTAL = Counter(
    "persona_response_total",
    "Chat responses served, labeled by the persona/role path that shaped them",
    ["user_role", "pipeline"],
)


class PrometheusMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        path = scope.get("path", "")

        if path == settings.prometheus_path:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        request = Request(scope, receive)

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            status_code = 500
            raise
        finally:
            duration = time.perf_counter() - start
            endpoint = self._normalize_path(path)
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=str(status_code)).inc()
            REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)

    def _normalize_path(self, path: str) -> str:
        parts = path.strip("/").split("/")
        if len(parts) >= 3:
            return "/".join(parts[:3]) + "/*"
        return path


def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
