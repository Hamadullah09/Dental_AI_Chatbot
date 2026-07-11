import re
import base64
from pathlib import Path

import httpx
from openai import OpenAI, OpenAIError

from app.core.config import get_settings


THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
PLACEHOLDER_LINE_RE = re.compile(
    r"^\s*(direct answer|explanation|safety note)?\s*:?\s*"
    r"(\[[^\]]*(answer|point|bullet|safety|note|explanation)[^\]]*\]|"
    r"\([^\)]*(answer|point|bullet|safety|note|explanation)[^\)]*\))\s*[\"']?\s*$",
    re.IGNORECASE,
)
LEAKED_REASONING_PHRASES = [
    "let's structure",
    "we are not to show thinking",
    "the user asked",
    "important:",
    "content for explanation",
    "we need to",
    "let's write",
    "we reply",
    "but note",
    "double-checking rules",
    "final check",
    "drafting now",
    "we are to",
    "key points to cover",
    "format:",
    "we must emphasize",
    "what is dental caries",
    "do not mention backend",
    "do not claim the answer",
    "answer format",
    "answer in this format",
    "2-4 bullet points",
    "a note about safety",
    "start immediately with",
    "use exactly these headings",
]


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

    def generate(self, prompt: str, *, system_prompt: str, temperature: float = 0.2, top_p: float | None = None) -> str:
        if self.provider == "ollama":
            return self._generate_ollama(prompt, system_prompt=system_prompt, temperature=temperature, top_p=top_p)
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

    def _generate_ollama(self, prompt: str, *, system_prompt: str, temperature: float, top_p: float | None = None) -> str:
        base_url = self.settings.ollama_base_url.rstrip("/")
        payload = {
            "model": self.settings.ollama_model,
            "prompt": f"/no_think\n\n{system_prompt}\n\n{prompt}",
            "stream": False,
            "think": False,
            "keep_alive": getattr(self.settings, "ollama_keep_alive", "0s"),
            "options": {
                "temperature": temperature,
                "top_p": self.settings.ollama_top_p if top_p is None else top_p,
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
        answer = data.get("response", "").strip()
        return clean_llm_response(answer)

    def analyze_image(
        self,
        image_path: str,
        prompt: str,
        *,
        system_prompt: str,
        temperature: float = 0.0,
    ) -> str:
        if self.provider != "ollama":
            raise LLMGenerationError("Visual analysis requires Ollama.")
        image_bytes = read_image_as_base64(image_path)
        base_url = self.settings.ollama_base_url.rstrip("/")
        payload = {
            "model": self.settings.ollama_vision_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt, "images": [image_bytes]},
            ],
            "stream": False,
            "think": False,
            "keep_alive": getattr(self.settings, "ollama_keep_alive", "0s"),
            "options": {
                "temperature": temperature,
                "top_p": 0.8,
                "num_ctx": self.settings.ollama_num_ctx,
                "num_predict": min(self.settings.ollama_num_predict, 256),
            },
        }
        try:
            timeout = httpx.Timeout(
                timeout=float(getattr(self.settings, "ollama_vision_timeout_seconds", 90)),
                connect=5.0,
                read=float(getattr(self.settings, "ollama_vision_timeout_seconds", 90)),
                write=20.0,
                pool=5.0,
            )
            with httpx.Client(timeout=timeout) as client:
                tags_response = client.get(f"{base_url}/api/tags")
                tags_response.raise_for_status()
                response = client.post(f"{base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise LLMGenerationError(
                f"Ollama vision model is not reachable at {self.settings.ollama_base_url} "
                f"or model '{self.settings.ollama_vision_model}' is not available. {exc}"
            ) from exc
        message = data.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else ""
        return clean_llm_response(str(content or ""))

    def ollama_model_health(self) -> dict[str, object]:
        if self.provider != "ollama" or not self.settings.ollama_base_url:
            return {"status": "not_configured"}
        base_url = self.settings.ollama_base_url.rstrip("/")
        try:
            with httpx.Client(timeout=1.0) as client:
                response = client.get(f"{base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            return {"status": "unreachable", "error": exc.__class__.__name__}
        names = {str(model.get("name") or model.get("model") or "") for model in data.get("models", [])}
        return {
            "status": "ok",
            "text_model": self.settings.ollama_model,
            "text_model_available": self.settings.ollama_model in names,
            "vision_model": self.settings.ollama_vision_model,
            "vision_model_available": self.settings.ollama_vision_model in names,
        }


def read_image_as_base64(image_path: str) -> str:
    path = Path(image_path)
    if not path.exists():
        raise LLMGenerationError(f"Visual image file was not found: {image_path}")
    return base64.b64encode(path.read_bytes()).decode("ascii")


def clean_llm_response(response: str) -> str:
    cleaned = THINK_BLOCK_RE.sub("", response)
    cleaned = re.sub(r"^.*?</think>\s*", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    kept_lines = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        stripped_l = stripped.lower()
        if any(phrase in stripped.lower() for phrase in LEAKED_REASONING_PHRASES):
            continue
        if re.match(r"^\d+\.\s*then\b", stripped_l):
            continue
        if re.match(r"^\d+\.\s*\[?", stripped_l):
            continue
        if PLACEHOLDER_LINE_RE.match(stripped):
            continue
        if stripped_l.startswith("- do not "):
            continue
        if stripped_l in {'[answer]', '[safety note]', '[safety note]"', '[answer]"', "let", "let's"}:
            continue
        if "[answer]" in stripped_l or "[safety note]" in stripped_l or "[2-4 bullet points]" in stripped_l:
            continue
        if re.match(r"^-\s*\[point\s+\d+\]", stripped_l):
            continue
        kept_lines.append(line)
    cleaned = "\n".join(kept_lines).strip()
    answer_headings = list(re.finditer(r"\bDirect Answer\s*:", cleaned, flags=re.IGNORECASE))
    answer_heading = answer_headings[-1] if answer_headings else re.search(
        r"\b(Explanation|Safety Note)\s*:",
        cleaned,
        flags=re.IGNORECASE,
    )
    if answer_heading:
        cleaned = cleaned[answer_heading.start():]
    cleaned = re.sub(r"^\s*(final answer\s*:)\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()
