from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Dental AI Chatbot"
    environment: str = "development"
    api_prefix: str = "/api"
    cors_origins: List[str] = ["*"]

    database_url: str = "sqlite:///./dental_ai.db"

    jwt_secret_key: str = Field(default="change-me-in-production")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    allow_admin_registration: bool = False

    qdrant_url: str = "http://localhost:6333"
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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | List[str]) -> List[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
