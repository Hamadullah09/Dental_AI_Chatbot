import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def uuid_str() -> str:
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    admin = "admin"
    dentist = "dentist"
    student = "student"
    patient = "patient"


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class DocumentType(str, enum.Enum):
    guideline = "guideline"
    textbook = "textbook"
    patient_education = "patient_education"
    research_article = "research_article"
    other = "other"


class TrustLevel(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class ReviewStatus(str, enum.Enum):
    unreviewed = "unreviewed"
    reviewed = "reviewed"
    approved = "approved"
    rejected = "rejected"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.patient, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(back_populates="uploaded_by_user")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus), default=DocumentStatus.uploaded)
    title: Mapped[str | None] = mapped_column(String(500))
    canonical_title: Mapped[str | None] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(500))
    author_or_source: Mapped[str | None] = mapped_column(String(500))
    publisher: Mapped[str | None] = mapped_column(String(500))
    edition: Mapped[str | None] = mapped_column(String(255))
    publication_year: Mapped[int | None] = mapped_column(Integer)
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType), default=DocumentType.textbook)
    trust_level: Mapped[TrustLevel] = mapped_column(Enum(TrustLevel), default=TrustLevel.high)
    review_status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.approved)
    specialty: Mapped[str | None] = mapped_column(String(255))
    dental_specialty: Mapped[str | None] = mapped_column(String(255))
    topic: Mapped[str | None] = mapped_column(String(255))
    difficulty_level: Mapped[str | None] = mapped_column(String(100))
    language: Mapped[str | None] = mapped_column(String(100))
    file_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    duplicate_group_id: Mapped[str | None] = mapped_column(String(100))
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    extraction_method: Mapped[str | None] = mapped_column(String(100))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    ingestion_progress: Mapped[int] = mapped_column(Integer, default=0)
    ingestion_step: Mapped[str | None] = mapped_column(String(255))
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    ingestion_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingestion_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    uploaded_by_user: Mapped[User | None] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    ingestion_logs: Mapped[list["DocumentIngestionLog"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentIngestionLog.created_at",
    )


class DocumentIngestionLog(Base):
    __tablename__ = "document_ingestion_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="ingestion_logs")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    qdrant_point_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    quality_score: Mapped[float] = mapped_column(Float, default=1.0)
    is_noisy: Mapped[bool] = mapped_column(Boolean, default=False)
    noise_reasons: Mapped[str | None] = mapped_column(Text)
    canonical_document_title: Mapped[str | None] = mapped_column(String(500))
    section_title: Mapped[str | None] = mapped_column(String(500))
    chapter_title: Mapped[str | None] = mapped_column(String(500))
    dental_specialty: Mapped[str | None] = mapped_column(String(255))
    topic: Mapped[str | None] = mapped_column(String(255))
    difficulty_level: Mapped[str | None] = mapped_column(String(100))
    language: Mapped[str | None] = mapped_column(String(100))
    trust_level: Mapped[str | None] = mapped_column(String(20))
    review_status: Mapped[str | None] = mapped_column(String(30))
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="chunks")


class DocumentVisual(Base):
    __tablename__ = "document_visuals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    visual_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    document_name: Mapped[str] = mapped_column(String(500), nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    visual_type: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    image_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    caption_text: Mapped[str | None] = mapped_column(Text)
    nearby_text: Mapped[str | None] = mapped_column(Text)
    generated_description: Mapped[str | None] = mapped_column(Text)
    related_chunk_ids: Mapped[str | None] = mapped_column(Text)
    quality_score: Mapped[float] = mapped_column(Float, default=1.0)
    review_status: Mapped[str] = mapped_column(String(30), default="reviewed", nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship()


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["Message"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[ChatSession] = relationship(back_populates="messages")
    feedback: Mapped["Feedback | None"] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    message: Mapped[Message] = relationship(back_populates="feedback")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(36))
    details: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserActivity(Base):
    __tablename__ = "user_activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    details: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationMemory(Base):
    __tablename__ = "conversation_memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    memory_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    importance_score: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
