from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "", **kwargs: Any) -> str:
        ...

    @abstractmethod
    def generate_stream(self, prompt: str, system_prompt: str = "", **kwargs: Any):
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...


class OllamaProvider(LLMProvider):
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def provider_name(self) -> str:
        return "ollama"

    def generate(self, prompt: str, system_prompt: str = "", **kwargs: Any) -> str:
        import httpx

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        with httpx.Client(timeout=self.settings.ollama_timeout_seconds) as client:
            response = client.post(
                f"{self.settings.ollama_base_url}/api/chat",
                json={
                    "model": kwargs.get("model", self.settings.ollama_model),
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "num_ctx": self.settings.ollama_num_ctx,
                        "num_predict": self.settings.ollama_num_predict,
                        "top_p": self.settings.ollama_top_p,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")

    def generate_stream(self, prompt: str, system_prompt: str = "", **kwargs: Any):
        import httpx

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        with httpx.Client(timeout=self.settings.ollama_timeout_seconds) as client:
            with client.stream(
                "POST",
                f"{self.settings.ollama_base_url}/api/chat",
                json={
                    "model": kwargs.get("model", self.settings.ollama_model),
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "num_ctx": self.settings.ollama_num_ctx,
                        "num_predict": self.settings.ollama_num_predict,
                        "top_p": self.settings.ollama_top_p,
                    },
                },
            ) as response:
                for line in response.iter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content

    def is_available(self) -> bool:
        import httpx
        try:
            with httpx.Client(timeout=self.settings.ollama_health_check_timeout) as client:
                response = client.get(f"{self.settings.ollama_base_url}/api/tags")
                return response.is_success
        except Exception:
            return False


class OpenAIProvider(LLMProvider):
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def provider_name(self) -> str:
        return "openai"

    def generate(self, prompt: str, system_prompt: str = "", **kwargs: Any) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.settings.openai_api_key)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=kwargs.get("model", self.settings.openai_model),
            messages=messages,
            temperature=kwargs.get("temperature", self.settings.openai_temperature),
            max_tokens=kwargs.get("max_tokens", self.settings.ollama_num_predict),
        )
        return response.choices[0].message.content or ""

    def generate_stream(self, prompt: str, system_prompt: str = "", **kwargs: Any):
        from openai import OpenAI

        client = OpenAI(api_key=self.settings.openai_api_key)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        stream = client.chat.completions.create(
            model=kwargs.get("model", self.settings.openai_model),
            messages=messages,
            temperature=kwargs.get("temperature", self.settings.openai_temperature),
            max_tokens=kwargs.get("max_tokens", self.settings.ollama_num_predict),
            stream=True,
        )
        for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content

    def is_available(self) -> bool:
        return bool(self.settings.openai_api_key)


class ModelRouter:
    def __init__(self) -> None:
        self.providers: dict[str, LLMProvider] = {}
        self._register_providers()

    def _register_providers(self) -> None:
        self.providers["ollama"] = OllamaProvider()
        self.providers["openai"] = OpenAIProvider()

    def get_provider(self, task: str = "text", preferred: str | None = None) -> LLMProvider:
        settings = get_settings()

        if preferred and preferred in self.providers:
            provider = self.providers[preferred]
            if provider.is_available():
                return provider

        if task == "vision":
            if settings.ollama_vision_model:
                return self.providers["ollama"]
            if settings.openai_api_key:
                return self.providers["openai"]

        if settings.llm_provider in self.providers:
            provider = self.providers[settings.llm_provider]
            if provider.is_available():
                return provider

        for name, provider in self.providers.items():
            if provider.is_available():
                logger.info(f"Fallback to provider: {name}")
                return provider

        raise RuntimeError("No LLM provider available")

    def generate(self, prompt: str, system_prompt: str = "", task: str = "text", **kwargs: Any) -> str:
        start = time.perf_counter()
        provider = self.get_provider(task=task, preferred=kwargs.pop("provider", None))
        result = provider.generate(prompt, system_prompt=system_prompt, **kwargs)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(f"LLM generation: {provider.provider_name} in {duration_ms:.1f}ms, {len(result)} chars")
        return result

    def generate_stream(self, prompt: str, system_prompt: str = "", task: str = "text", **kwargs: Any):
        provider = self.get_provider(task=task, preferred=kwargs.pop("provider", None))
        return provider.generate_stream(prompt, system_prompt=system_prompt, **kwargs)

    def is_available(self, provider_name: str | None = None) -> bool:
        if provider_name:
            provider = self.providers.get(provider_name)
            return provider.is_available() if provider else False
        return any(p.is_available() for p in self.providers.values())


model_router = ModelRouter()
