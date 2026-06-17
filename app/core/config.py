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

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    upload_dir: Path = Path("uploaded_docs")
    chunk_size: int = 1000
    chunk_overlap: int = 180

    medical_disclaimer: str = (
        "Dental AI is for education and clinical decision support only. "
        "It does not replace diagnosis, treatment planning, or emergency care from a licensed dentist."
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
