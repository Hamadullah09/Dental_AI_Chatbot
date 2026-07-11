from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Dental AI Chatbot"
    environment: str = "development"
    api_prefix: str = "/api"
    cors_origins: str = "*"

    database_url: str = "sqlite:///./dental_ai.db"

    jwt_secret_key: str = Field(default="change-me-in-production")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    allow_admin_registration: bool = False
    admin_email: str | None = None
    admin_password: str | None = None
    admin_full_name: str = "System Administrator"

    qdrant_url: str | None = "http://localhost:6333"
    qdrant_local_path: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection: str = "dental_docs"
    embedding_model_name: str = "all-MiniLM-L6-v2"
    retrieval_top_k: int = 5
    enable_keyword_search: bool = True
    keyword_search_scan_limit: int = 4000
    rag_mode: str = "simple"
    retrieval_min_relevance_score: float = 1.1
    allow_general_fallback: bool = True
    enable_memory: bool = True
    enable_query_rewriting: bool = True
    enable_adjacent_chunk_expansion: bool = True
    enable_hyde: bool = False
    enable_self_check: bool = False
    enable_bge_reranker: bool = False
    bge_reranker_model: str = "BAAI/bge-reranker-v2-m3"
    multi_query_max_variants: int = 4
    web_search_provider: str = "tavily"
    tavily_api_key: str | None = None
    brave_search_api_key: str | None = None
    google_search_api_key: str | None = None
    google_search_engine_id: str | None = None
    web_search_max_results: int = 5
    web_search_trusted_domains: str = (
        "who.int,cdc.gov,nih.gov,ncbi.nlm.nih.gov,nhs.uk,ada.org,nice.org.uk,fda.gov"
    )

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_model_fallbacks: str = "gpt-4.1-mini,gpt-4o-mini,gpt-3.5-turbo"
    llm_provider: str = "openai"
    ollama_num_ctx: int = 4096
    ollama_num_predict: int = 512
    ollama_top_p: float = 0.8
    ollama_timeout_seconds: int = 180
    ollama_vision_timeout_seconds: int = 90
    ollama_keep_alive: str = "0s"
    dataset_llm_provider: str = "ollama"
    dataset_generation_stale_minutes: int = 20
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:14b"
    ollama_vision_model: str = "qwen2.5vl:7b"

    upload_dir: Path = Path("uploaded_docs")
    extracted_visuals_dir: Path = Path("uploads/extracted_visuals")
    max_upload_mb: int = 200
    chunk_size: int = 1000
    chunk_overlap: int = 180
    embedding_batch_size: int = 64
    vector_upsert_batch_size: int = 128
    enable_multimodal_rag: bool = True
    visual_page_snapshot_zoom: float = 1.6
    visual_min_relevance_score: float = 0.95
    ocr_dpi: int = 250
    ocr_language: str = "eng"
    ocr_config: str = "--psm 6"
    tesseract_cmd: str | None = None
    poppler_path: str | None = None

    medical_disclaimer: str = (
        "Dental AI is for education and clinical decision support only. "
        "It does not replace diagnosis, treatment planning, or emergency care from a licensed dentist."
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def web_search_domain_list(self) -> list[str]:
        return [item.strip() for item in self.web_search_trusted_domains.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
