import re

import httpx
from openai import OpenAI, OpenAIError

from app.core.config import get_settings


THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)


class LLMGenerationError(RuntimeError):
    pass


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.provider = self.settings.llm_provider.lower().strip()
        self.openai_client = OpenAI(api_key=self.settings.openai_api_key) if self.settings.openai_api_key else None

    @property
    def is_configured(self) -> bool:
        if self.provider == "ollama":
            return bool(self.settings.ollama_base_url and self.settings.ollama_model)
        if self.provider == "openai":
            return bool(self.openai_client)
        return False

    def generate(self, prompt: str, *, system_prompt: str, temperature: float = 0.2) -> str:
        if self.provider == "ollama":
            return self._generate_ollama(prompt, system_prompt=system_prompt, temperature=temperature)
        if self.provider == "openai":
            return self._generate_openai(prompt, system_prompt=system_prompt, temperature=temperature)
        raise LLMGenerationError("LLM_PROVIDER must be 'openai' or 'ollama'.")

    def _generate_openai(self, prompt: str, *, system_prompt: str, temperature: float) -> str:
        if not self.openai_client:
            raise LLMGenerationError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")
        try:
            response = self.openai_client.chat.completions.create(
                model=self.settings.openai_model,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
        except OpenAIError as exc:
            raise LLMGenerationError(str(exc)) from exc
        return clean_llm_response(response.choices[0].message.content or "")

    def _generate_ollama(self, prompt: str, *, system_prompt: str, temperature: float) -> str:
        base_url = self.settings.ollama_base_url.rstrip("/")
        payload = {
            "model": self.settings.ollama_model,
            "prompt": f"{system_prompt}\n\n{prompt}",
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_ctx": self.settings.ollama_num_ctx,
                "num_predict": self.settings.ollama_num_predict,
            },
        }
        try:
            timeout = httpx.Timeout(
                timeout=float(self.settings.ollama_timeout_seconds),
                connect=5.0,
                read=float(self.settings.ollama_timeout_seconds),
                write=10.0,
                pool=5.0,
            )
            with httpx.Client(timeout=timeout) as client:
                tags_response = client.get(f"{base_url}/api/tags")
                tags_response.raise_for_status()
                response = client.post(
                    f"{base_url}/api/generate",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise LLMGenerationError(
                f"Ollama is not reachable at {self.settings.ollama_base_url} "
                f"or model '{self.settings.ollama_model}' is not available. {exc}"
            ) from exc
        return clean_llm_response(str(data.get("response") or ""))


def clean_llm_response(response: str) -> str:
    cleaned = THINK_BLOCK_RE.sub("", response)
    cleaned = re.sub(r"^\s*(final answer\s*:)\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()
