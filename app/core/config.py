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
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    jwt_secret_key: str = Field(default="change-me-in-production")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    refresh_token_expire_days: int = 7
    allow_admin_registration: bool = False
    admin_email: str | None = None
    admin_password: str | None = None
    admin_full_name: str = "System Administrator"

    redis_url: str = "redis://redis:6379/0"
    redis_max_connections: int = 20
    redis_cache_ttl_seconds: int = 3600
    redis_session_ttl_seconds: int = 86400
    redis_rate_limit_ttl_seconds: int = 60

    qdrant_url: str | None = "http://localhost:6333"
    qdrant_local_path: str | None = None
    qdrant_api_key: str | None = None
    qdrant_timeout_seconds: int = 120
    qdrant_collection: str = "dental_docs"
    qdrant_visual_collection: str = "dental_visuals"
    embedding_model_name: str = "all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    retrieval_top_k: int = 5
    retrieval_candidate_multiplier: int = 4
    retrieval_min_candidates: int = 20
    retrieval_max_results: int = 5
    retrieval_min_results: int = 3
    enable_keyword_search: bool = True
    keyword_search_scan_limit: int = 4000
    rag_mode: str = "simple"
    retrieval_min_relevance_score: float = 1.1
    allow_general_fallback: bool = True
    enable_memory: bool = True
    enable_query_rewriting: bool = True
    enable_adjacent_chunk_expansion: bool = True
    adjacent_chunk_window: int = 1
    enable_hyde: bool = False
    enable_self_check: bool = False
    self_check_ungrounded_threshold: float = 0.25
    enable_bge_reranker: bool = False
    bge_reranker_model: str = "BAAI/bge-reranker-v2-m3"
    bge_reranker_max_chunks: int = 40
    bge_reranker_max_chars: int = 1600
    multi_query_max_variants: int = 4
    multi_query_confidence_threshold: float = 1.35
    hyde_confidence_threshold: float = 1.35
    hyde_max_passage_chars: int = 900
    corrective_confidence_threshold: float = 1.35
    memory_context_max_chars: int = 320
    memory_context_messages: int = 4
    conversation_history_limit: int = 8
    rerank_trust_high_boost: float = 0.25
    rerank_trust_medium_boost: float = 0.1
    rerank_trust_low_boost: float = -0.25
    rerank_approved_boost: float = 0.2
    rerank_quality_baseline: float = 0.6
    rerank_quality_multiplier: float = 0.5
    rerank_keyword_weight: float = 0.35
    rerank_lexical_weight: float = 0.2
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    context_compression_max_chars: int = 1000
    web_search_provider: str = "tavily"
    tavily_api_key: str | None = None
    brave_search_api_key: str | None = None
    google_search_api_key: str | None = None
    google_search_engine_id: str | None = None
    web_search_max_results: int = 5
    web_search_timeout_seconds: int = 20
    web_search_max_result_chars: int = 1800
    web_search_max_results_cap: int = 10
    web_search_trusted_domains: str = (
        "who.int,cdc.gov,nih.gov,ncbi.nlm.nih.gov,nhs.uk,ada.org,nice.org.uk,fda.gov"
    )

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_model_fallbacks: str = "gpt-4.1-mini,gpt-4o-mini,gpt-3.5-turbo"
    openai_temperature: float = 0.2
    llm_provider: str = "openai"
    ollama_num_ctx: int = 4096
    ollama_num_predict: int = 512
    ollama_top_p: float = 0.8
    ollama_timeout_seconds: int = 300
    ollama_vision_timeout_seconds: int = 180
    ollama_keep_alive: str = "0s"
    ollama_connect_timeout: float = 5.0
    ollama_write_timeout: float = 10.0
    ollama_pool_timeout: float = 5.0
    ollama_vision_connect_timeout: float = 5.0
    ollama_vision_write_timeout: float = 20.0
    ollama_vision_pool_timeout: float = 5.0
    ollama_health_check_timeout: float = 1.0
    dataset_llm_provider: str = "ollama"
    dataset_generation_stale_minutes: int = 20
    dataset_generation_temperature: float = 0.2
    dataset_generation_chunk_text_max_chars: int = 3500
    dataset_output_dir: str = "."
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:14b"
    ollama_vision_model: str = "qwen2.5vl:7b"

    upload_dir: Path = Path("uploaded_docs")
    extracted_visuals_dir: Path = Path("uploads/extracted_visuals")
    max_upload_mb: int = 200
    ingestion_timeout_seconds: int = 14400
    chunk_size: int = 1000
    chunk_overlap: int = 180
    chunk_min_words: int = 5
    chunk_min_quality_score: float = 0.6
    embedding_batch_size: int = 64
    vector_upsert_batch_size: int = 128
    vector_upsert_max_retries: int = 3
    vector_upsert_retry_delay_multiplier: float = 0.5
    db_commit_max_retries: int = 8
    db_commit_retry_delay: float = 0.25
    enable_multimodal_rag: bool = True
    visual_page_snapshot_zoom: float = 1.6
    visual_min_relevance_score: float = 0.95
    visual_candidate_multiplier: int = 4
    visual_min_candidates: int = 12
    visual_chunk_linked_multiplier: int = 3
    visual_chunk_linked_min: int = 8
    visual_wants_answer_threshold_reduction: float = 0.75
    visual_same_page_boost: float = 0.12
    visual_max_chunk_linked_rows: int = 250
    visual_max_to_analyze: int = 2
    visual_observation_max_words: int = 80
    visual_observation_max_chars: int = 700
    visual_caption_max_chars: int = 320
    visual_nearby_text_max_chars: int = 1200
    visual_max_tables_per_page: int = 5
    visual_table_image_dpi: int = 150
    visual_quality_baseline: float = 0.45
    visual_caption_boost: float = 0.3
    visual_nonsnapshot_boost: float = 0.15
    visual_nearby_text_word_threshold: int = 35
    visual_nearby_text_boost: float = 0.1
    visual_rerank_wants_answer_boost: float = 0.5
    visual_rerank_same_page_boost: float = 0.45
    visual_rerank_related_chunk_boost: float = 0.55
    visual_rerank_caption_boost: float = 0.25
    visual_rerank_quality_baseline: float = 0.45
    visual_rerank_quality_multiplier: float = 0.45
    visual_rerank_lexical_weight: float = 0.18
    ocr_dpi: int = 250
    ocr_language: str = "eng"
    ocr_config: str = "--psm 6"
    ocr_min_line_length: int = 4
    ocr_garbage_penalty: float = 0.45
    tesseract_cmd: str | None = None
    poppler_path: str | None = None

    rate_limit_requests_per_minute: int = 60
    rate_limit_chat_per_minute: int = 20
    rate_limit_auth_per_minute: int = 10
    rate_limit_upload_per_minute: int = 5

    streaming_enabled: bool = True
    streaming_chunk_size: int = 10
    streaming_timeout_seconds: int = 300

    log_level: str = "INFO"
    log_format: str = "json"
    log_file: str | None = None
    log_request_id: bool = True

    prometheus_enabled: bool = True
    prometheus_path: str = "/metrics"

    worker_concurrency: int = 4
    worker_max_retries: int = 3
    worker_retry_delay_seconds: int = 5

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

    @property
    def openai_model_fallback_list(self) -> list[str]:
        return [item.strip() for item in self.openai_model_fallbacks.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
