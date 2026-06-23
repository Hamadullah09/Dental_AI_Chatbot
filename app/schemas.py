from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.models import DocumentStatus, DocumentType, ReviewStatus, TrustLevel, UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None
    role: UserRole = Field(default=UserRole.patient, description="Public registration supports patient, student, and dentist roles.")


class UserRead(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None
    role: UserRole
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SourceCitation(BaseModel):
    document_id: str | None = None
    document_name: str
    page_number: int | None = None
    chunk_index: int | None = None
    score: float | None = None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: str | None = None
    document_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=12)
    document_types: list[DocumentType] | None = None
    trust_levels: list[TrustLevel] | None = None
    review_status: ReviewStatus | None = ReviewStatus.approved
    min_year: int | None = Field(default=None, ge=1800, le=2100)


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    message_id: str
    sources: list[SourceCitation]
    disclaimer: str


class MessageRead(BaseModel):
    id: str
    role: str
    content: str
    sources: list[dict[str, Any]] = []
    created_at: datetime


class ChatSessionRead(BaseModel):
    id: str
    title: str | None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageRead] = []


class DocumentRead(BaseModel):
    id: str
    filename: str
    original_filename: str
    title: str | None
    author_or_source: str | None
    edition: str | None
    publication_year: int | None
    document_type: DocumentType
    trust_level: TrustLevel
    review_status: ReviewStatus
    specialty: str | None
    language: str | None
    file_hash: str | None
    status: DocumentStatus
    chunk_count: int
    error_message: str | None
    ingestion_progress: int = 0
    ingestion_step: str | None = None
    ocr_used: bool = False
    ingestion_started_at: datetime | None = None
    ingestion_completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentIngestionLogRead(BaseModel):
    id: str
    document_id: str
    level: str
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetGenerationRequest(BaseModel):
    document_id: str | None = None
    limit: int | None = Field(default=25, ge=1, le=500)
    examples_per_chunk: int = Field(default=5, ge=1, le=10)
    min_quality: float = Field(default=0.6, ge=0.0, le=1.0)
    include_noisy: bool = False


class DatasetGenerationStatus(BaseModel):
    state: str
    processed_chunks: int = 0
    generated_items: int = 0
    skipped_chunks: int = 0
    duplicate_chunks: int = 0
    removed_existing_rows: int = 0
    document_id: str | None = None
    document_name: str | None = None
    output_path: str
    skipped_path: str
    review_csv_path: str | None = None
    provider: str | None = None
    message: str | None = None
    updated_at: str | None = None


class FeedbackCreate(BaseModel):
    message_id: str
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackRead(BaseModel):
    id: str
    message_id: str
    rating: int
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
