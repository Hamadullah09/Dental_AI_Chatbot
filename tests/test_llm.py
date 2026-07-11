import httpx

from app.services.llm import LLMService, clean_llm_response


def test_ollama_generation_uses_response_field_and_ignores_thinking(monkeypatch):
    class FakeResponse:
        def __init__(self, payload=None):
            self.payload = payload or {}

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def get(self, url):
            return FakeResponse({"models": [{"name": "qwen3:4b"}]})

        def post(self, url, json):
            return FakeResponse(
                {
                    "thinking": "This internal chain of thought must never appear.",
                    "response": "Direct Answer: Tooth decay is damage caused by acids.",
                }
            )

    monkeypatch.setattr(httpx, "Client", FakeClient)
    service = object.__new__(LLMService)
    service.settings = type(
        "Settings",
        (),
        {
            "ollama_base_url": "http://100.79.127.70:11434",
            "ollama_model": "qwen3:4b",
            "ollama_top_p": 0.8,
            "ollama_num_ctx": 4096,
            "ollama_num_predict": 512,
            "ollama_timeout_seconds": 180,
        },
    )()

    answer = service._generate_ollama("Question", system_prompt="System", temperature=0.1)

    assert "Tooth decay" in answer
    assert "thinking" not in answer.lower()
    assert "chain of thought" not in answer.lower()


def test_ollama_prompt_disables_qwen_thinking(monkeypatch):
    captured = {}

    class FakeResponse:
        def __init__(self, payload=None):
            self.payload = payload or {}

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def get(self, url):
            return FakeResponse({"models": [{"name": "qwen3:4b"}]})

        def post(self, url, json):
            captured["payload"] = json
            return FakeResponse({"response": "Direct Answer: Done."})

    monkeypatch.setattr(httpx, "Client", FakeClient)
    service = object.__new__(LLMService)
    service.settings = type(
        "Settings",
        (),
        {
            "ollama_base_url": "http://100.79.127.70:11434",
            "ollama_model": "qwen3:4b",
            "ollama_top_p": 0.8,
            "ollama_num_ctx": 4096,
            "ollama_num_predict": 512,
            "ollama_timeout_seconds": 180,
        },
    )()

    service._generate_ollama("Question", system_prompt="System", temperature=0.1)

    assert captured["payload"]["think"] is False
    assert captured["payload"]["prompt"].startswith("/no_think")


def test_clean_llm_response_removes_stray_qwen_thinking_prefix():
    raw = """
Okay, the user wants me to explain dental caries. I need to follow the rules.
*Double-checking rules*
</think>

Direct Answer:
Dental caries is tooth decay.

Explanation:
It happens when bacteria and sugars produce acids that weaken tooth enamel.
"""

    cleaned = clean_llm_response(raw)

    assert cleaned.startswith("Direct Answer:")
    assert "Okay, the user wants" not in cleaned
    assert "Double-checking" not in cleaned
    assert "</think>" not in cleaned


def test_clean_llm_response_removes_preface_before_answer_heading():
    raw = """
Here is the answer after considering the user's request.

Direct Answer:
Dental caries is tooth decay.
"""

    cleaned = clean_llm_response(raw)

    assert cleaned == "Direct Answer:\nDental caries is tooth decay."


def test_clean_llm_response_removes_common_leaked_reasoning_lines():
    raw = """
Let's structure the answer clearly.
The user asked in English, so respond in English.
Important: do not show thinking.

Direct Answer:
Dental caries is tooth decay.
"""

    cleaned = clean_llm_response(raw)

    assert cleaned == "Direct Answer:\nDental caries is tooth decay."


def test_clean_llm_response_removes_copied_format_instructions():
    raw = """
Direct Answer: [answer]"

2. Then "Explanation:" followed by a list of 4 points

3. Then "Safety Note: [safety note]"

- Do not mention backend, OpenAI, model errors, etc.
We are to explain dental caries in detail.
Key points to cover (4 points):

Direct Answer:
Dental caries is tooth decay.
"""

    cleaned = clean_llm_response(raw)

    assert "Then \"Explanation" not in cleaned
    assert "We are to explain" not in cleaned
    assert "[answer]" not in cleaned
