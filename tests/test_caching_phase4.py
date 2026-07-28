from app.services.retrieval_cache import (
    bump_generation,
    cache_chunks,
    current_generation,
    get_cached_chunks,
)


def test_retrieval_cache_round_trip():
    chunks = [{"text": "Fluoride prevents cavities.", "citation": {"document_name": "Textbook.pdf"}}]
    cache_chunks("How does fluoride help?", "multi_query", 5, {"user_role": "patient"}, chunks)
    result = get_cached_chunks("How does fluoride help?", "multi_query", 5, {"user_role": "patient"})
    assert result == chunks


def test_retrieval_cache_misses_on_different_filters():
    chunks = [{"text": "x"}]
    cache_chunks("q", "multi_query", 5, {"user_role": "patient"}, chunks)
    assert get_cached_chunks("q", "multi_query", 5, {"user_role": "dentist"}) is None


def test_bump_generation_invalidates_prior_cache_entries():
    chunks = [{"text": "stale chunk"}]
    cache_chunks("cache invalidation test question", "simple", 5, {}, chunks)
    assert get_cached_chunks("cache invalidation test question", "simple", 5, {}) == chunks

    before = current_generation()
    bump_generation()
    assert current_generation() == before + 1

    # Same question/filters, but the generation bump means this now misses.
    assert get_cached_chunks("cache invalidation test question", "simple", 5, {}) is None


def test_embedding_cache_returns_same_vector_for_identical_text():
    from app.services.embeddings import ResilientEmbeddingModel

    class FakeModel:
        calls = 0

        def encode(self, texts):
            FakeModel.calls += 1
            return __import__("numpy").array([[1.0, 2.0, 3.0]])

    wrapped = ResilientEmbeddingModel(FakeModel(), model_name="fake-model-for-test")
    first = wrapped.encode(["a repeated question about cavities"])
    second = wrapped.encode(["a repeated question about cavities"])

    assert FakeModel.calls == 1, "second call should have been served from cache"
    assert (first == second).all()
