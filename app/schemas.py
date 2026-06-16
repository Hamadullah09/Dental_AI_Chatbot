from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.models import DocumentStatus, UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None
    role: UserRole = UserRole.patient


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
    top_k: int | None = Field(default=None, ge=1, le=12)


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
    status: DocumentStatus
    chunk_count: int
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


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
