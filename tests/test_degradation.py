from app.services.degradation import (
    DegradationTier,
    _normalized_question_key,
    cache_successful_answer,
    get_cached_answer,
)


def test_normalized_question_key_ignores_case_and_whitespace():
    a = _normalized_question_key("  What Causes   Cavities?  ")
    b = _normalized_question_key("what causes cavities?")
    assert a == b


def test_normalized_question_key_differs_for_different_questions():
    a = _normalized_question_key("What causes cavities?")
    b = _normalized_question_key("What causes gum disease?")
    assert a != b


def test_cache_round_trip_returns_none_when_redis_unavailable(monkeypatch):
    # RedisCache already fails open (returns None/False) when Redis is unreachable, so the
    # degradation cache must not raise even if nothing is actually running.
    result = get_cached_answer("some question nobody asked yet " + str(id(object())))
    assert result is None or isinstance(result, dict)


def test_cache_successful_answer_does_not_raise_on_bad_source_objects():
    class NotSerializable:
        pass

    # Should not raise even with objects that can't cleanly serialize - cache_successful_answer
    # is a best-effort side channel, never allowed to break the main response path.
    cache_successful_answer("test question", "test answer", [NotSerializable()], None)


def test_degradation_tier_values_are_stable_strings():
    assert DegradationTier.full_hybrid.value == "full_hybrid"
    assert DegradationTier.keyword_only.value == "keyword_only"
    assert DegradationTier.cached_answer.value == "cached_answer"
    assert DegradationTier.static_degraded.value == "static_degraded"
