"""Tests for app/agent/graph.py - previously the only RAG pipeline component with zero
direct test coverage (docs/GAP_AUDIT_PHASE0.md finding #9). Focuses on node-level behavior
with external calls mocked, plus the graph's structural contract (memory node wired in,
error-handling node reachable) rather than a full end-to-end run against real Qdrant/Ollama.
"""

from app.agent.state import AgentState
from app.core.resilience import CircuitBreakerOpenError
from app.services.degradation import DegradationTier


def test_build_langgraph_registers_memory_node():
    from app.agent.graph import build_langgraph

    graph = build_langgraph()
    node_names = set(graph.get_graph().nodes.keys())
    assert "load_memory_context" in node_names, (
        "load_memory_context must be wired into the graph - "
        "app/agent/nodes/memory.py was found orphaned and dead (finding #11); "
        "the fix wires the working MemoryService in as a real node instead."
    )


def test_load_memory_context_skips_when_disabled(monkeypatch):
    from app.agent.graph import load_memory_context
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "enable_memory", False)

    state = AgentState(question="What is a cavity?", user_id="user-1")
    result = load_memory_context(state)

    assert result.memory_context == ""
    assert result.trace_log[-1]["node"] == "memory_loader"
    assert result.trace_log[-1]["status"] == "skipped"


def test_load_memory_context_skips_without_user_id(monkeypatch):
    from app.agent.graph import load_memory_context
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "enable_memory", True)

    state = AgentState(question="What is a cavity?", user_id=None)
    result = load_memory_context(state)

    assert result.memory_context == ""


def test_retrieve_chunks_degrades_to_keyword_only_when_qdrant_circuit_open(monkeypatch):
    from app.agent import graph as graph_module

    class FakeRAG:
        def retrieve(self, *args, **kwargs):
            raise CircuitBreakerOpenError("qdrant")

    fake_chunk = type(
        "FakeChunk",
        (),
        {
            "text": "Fluoride prevents cavities.",
            "citation": type(
                "Citation",
                (),
                {
                    "source_type": "pdf",
                    "document_id": "doc-1",
                    "document_name": "Textbook.pdf",
                    "page_number": 3,
                    "chunk_index": 1,
                    "score": 0.8,
                },
            )(),
            "vector_score": 0.0,
            "keyword_score": 0.8,
            "rerank_score": 0.0,
        },
    )()

    monkeypatch.setattr(graph_module, "_run_requested_retrieval_mode", lambda *a, **k: (_ for _ in ()).throw(CircuitBreakerOpenError("qdrant")))
    monkeypatch.setattr("app.services.degradation.keyword_only_retrieve", lambda rag, q, k, f: [fake_chunk])
    monkeypatch.setattr("app.services.rag.RAGService", lambda: FakeRAG())

    state = AgentState(question="How does fluoride help teeth?")
    result = graph_module.retrieve_chunks(state)

    assert result.degradation_tier == DegradationTier.keyword_only.value
    assert len(result.retrieved_chunks) == 1
    assert result.retrieved_chunks[0]["citation"]["document_name"] == "Textbook.pdf"


def test_retrieve_chunks_falls_back_to_static_degraded_on_total_failure(monkeypatch):
    from app.agent import graph as graph_module

    def _raise(*args, **kwargs):
        raise RuntimeError("everything is down")

    monkeypatch.setattr("app.services.rag.RAGService", _raise)

    state = AgentState(question="How does fluoride help teeth?")
    result = graph_module.retrieve_chunks(state)

    assert result.degradation_tier == "static_degraded"
    assert result.retrieved_chunks == []
    assert result.error


def test_populate_sources_and_visuals_caps_at_five_and_two():
    from app.agent.graph import populate_sources_and_visuals

    state = AgentState(question="q")
    state.reranked_chunks = [
        {"citation": {"document_name": f"doc-{i}", "score": 0.5}} for i in range(10)
    ]
    state.reranked_visuals = [
        {"visual_id": f"v-{i}", "document_name": f"doc-{i}"} for i in range(10)
    ]

    populate_sources_and_visuals(state)

    assert len(state.sources) == 5
    assert len(state.visuals) == 2


def test_run_self_check_and_adjust_answer_is_exception_safe(monkeypatch):
    from app.agent.graph import run_self_check_and_adjust_answer

    def _raise(*args, **kwargs):
        raise RuntimeError("self-check backend down")

    monkeypatch.setattr("app.services.rag.RAGService", _raise)

    state = AgentState(question="q")
    state.answer = "Some answer."
    state.reranked_chunks = []

    # Must not raise even if the self-check machinery itself fails.
    run_self_check_and_adjust_answer(state)
    assert state.answer == "Some answer."
