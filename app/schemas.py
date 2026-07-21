from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field

from app.models import (
    AppointmentStatus,
    DentistSpecialization,
    DocumentStatus,
    DocumentType,
    ReviewStatus,
    TrustLevel,
    UserRole,
)


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
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: UserRead


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SourceCitation(BaseModel):
    source_type: str = "pdf"
    document_id: str | None = None
    document_name: str
    page_number: int | None = None
    chunk_index: int | None = None
    url: str | None = None
    score: float | None = None


class VisualCitation(BaseModel):
    visual_id: str
    document_id: str | None = None
    document_name: str
    page_number: int | None = None
    visual_type: str = "unknown"
    image_path: str
    image_url: str
    caption_text: str | None = None
    generated_description: str | None = None
    score: float | None = None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: str | None = None
    document_id: str | None = None
    search_web: bool = False
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
    visuals: list[VisualCitation] = []
    answer_mode: str = "rag_grounded"
    disclaimer: str


class MessageRead(BaseModel):
    id: str
    role: str
    content: str
    sources: list[dict[str, Any]] = []
    visuals: list[dict[str, Any]] = []
    created_at: datetime


class ChatSessionRead(BaseModel):
    id: str
    title: str | None
    archived: bool = False
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


class TimeSlot(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: str
    end_time: str
    is_available: bool = True


class DentistBase(BaseModel):
    full_name: str = Field(min_length=1)
    qualification: str | None = None
    degrees: str | None = None
    specialization: list[DentistSpecialization] = []
    experience_years: int | None = Field(default=None, ge=0)
    clinic_name: str | None = None
    consultation_fee: float | None = Field(default=None, ge=0)
    available_timings: list[TimeSlot] = []
    languages: list[str] = []
    biography: str | None = None
    profile_picture_url: str | None = None
    is_available: bool = True
    source_url: str | None = None
    department: str | None = None
    hospital: str | None = None
    gender: str | None = None
    clinical_interests: str | None = None
    research_interests: str | None = None
    education: str | None = None
    profile_url: str | None = None
    image_url: str | None = None


class DentistCreate(DentistBase):
    pass


class DentistUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1)
    qualification: str | None = None
    specialization: list[DentistSpecialization] | None = None
    experience_years: int | None = Field(default=None, ge=0)
    clinic_name: str | None = None
    consultation_fee: float | None = Field(default=None, ge=0)
    available_timings: list[TimeSlot] | None = None
    languages: list[str] | None = None
    biography: str | None = None
    profile_picture_url: str | None = None
    is_available: bool | None = None
    source_url: str | None = None


class DentistRead(DentistBase):
    id: str
    slug: str | None = None
    rating: float
    review_count: int
    department: str | None = None
    hospital: str | None = None
    gender: str | None = None
    degrees: str | None = None
    clinical_interests: str | None = None
    research_interests: str | None = None
    education: str | None = None
    consultation_timings: str | None = None
    available_days: str | None = None
    appointment_url: str | None = None
    profile_url: str | None = None
    image_url: str | None = None
    image_path: str | None = None
    data_version: int = 1
    last_scraped_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DentistSearchParams(BaseModel):
    query: str | None = None
    specialization: DentistSpecialization | None = None
    clinic: str | None = None
    min_experience: int | None = Field(default=None, ge=0)
    max_fee: float | None = Field(default=None, ge=0)
    language: str | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=50)


class DentistSearchResult(BaseModel):
    dentists: list[DentistRead]
    total: int
    page: int
    limit: int
    total_pages: int


class AppointmentBase(BaseModel):
    dentist_id: str
    appointment_date: datetime
    duration_minutes: int = Field(default=30, ge=15, le=120)
    notes: str | None = None
    reason: str | None = None


class AppointmentCreate(AppointmentBase):
    patient_id: str | None = None


class AppointmentUpdate(BaseModel):
    appointment_date: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=120)
    status: AppointmentStatus | None = None
    notes: str | None = None
    reason: str | None = None
    rejection_reason: str | None = None


class AppointmentRead(BaseModel):
    id: str
    patient_id: str
    dentist_id: str
    appointment_date: datetime
    appointment_end: datetime
    duration_minutes: int = 30
    status: AppointmentStatus
    chief_complaint: str | None = None
    reason: str | None = None
    notes: str | None = None
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    patient: Optional["UserRead"] = None
    dentist: Optional["DentistRead"] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, obj: "Appointment") -> "AppointmentRead":
        duration = int((obj.appointment_end - obj.appointment_date).total_seconds() // 60)
        return cls(
            id=obj.id,
            patient_id=obj.patient_id,
            dentist_id=obj.dentist_id,
            appointment_date=obj.appointment_date,
            appointment_end=obj.appointment_end,
            duration_minutes=duration,
            status=obj.status,
            chief_complaint=obj.chief_complaint,
            reason=obj.chief_complaint,
            notes=obj.notes,
            rejection_reason=obj.cancellation_reason,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            patient=obj.patient if hasattr(obj, "_sa_instance_state") and obj.patient else None,
            dentist=obj.dentist if hasattr(obj, "_sa_instance_state") and obj.dentist else None,
        )


class AppointmentListParams(BaseModel):
    status: AppointmentStatus | None = None
    dentist_id: str | None = None
    patient_id: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=50)


class AppointmentSearchParams(BaseModel):
    status: AppointmentStatus | None = None
    dentist_id: str | None = None
    patient_id: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    query: str | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=50)


class AppointmentSearchResult(BaseModel):
    appointments: list[AppointmentRead]
    total: int
    page: int
    limit: int
    total_pages: int


class AppointmentStatusUpdate(BaseModel):
    status: AppointmentStatus
    reason: str | None = None


class PrescriptionSearchParams(BaseModel):
    patient_id: str | None = None
    dentist_id: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    query: str | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=50)


class PrescriptionBase(BaseModel):
    appointment_id: str
    diagnosis: str
    medicines: str
    dosage: str
    frequency: str
    duration: str
    instructions: str | None = None
    notes: str | None = None
    follow_up_date: datetime | None = None
    attachments: list[str] = []


class PrescriptionCreate(PrescriptionBase):
    pass


class PrescriptionUpdate(BaseModel):
    diagnosis: str | None = None
    medicines: str | None = None
    dosage: str | None = None
    frequency: str | None = None
    duration: str | None = None
    instructions: str | None = None
    notes: str | None = None
    follow_up_date: datetime | None = None
    attachments: list[str] | None = None


class PrescriptionRead(BaseModel):
    id: str
    patient_id: str
    dentist_id: str
    appointment_id: str
    diagnosis: str
    medicines: str
    dosage: str
    frequency: str
    duration: str
    instructions: str | None
    notes: str | None
    follow_up_date: datetime | None
    attachments: list[str] = []
    created_at: datetime
    updated_at: datetime
    patient: Optional["UserRead"] = None
    dentist: Optional["DentistRead"] = None
    appointment: Optional["AppointmentRead"] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, obj: "Prescription") -> "PrescriptionRead":
        def _split(val: str | None) -> list[str]:
            if not val:
                return []
            return [v.strip() for v in val.split(",") if v.strip()]

        return cls(
            id=obj.id,
            patient_id=obj.patient_id,
            dentist_id=obj.dentist_id,
            appointment_id=obj.appointment_id,
            diagnosis=obj.diagnosis,
            medicines=obj.medicines,
            dosage=obj.dosage,
            frequency=obj.frequency,
            duration=obj.duration,
            instructions=obj.instructions,
            notes=obj.notes,
            follow_up_date=obj.follow_up_date,
            attachments=_split(obj.attachment_path) if hasattr(obj, "attachment_path") else [],
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            patient=obj.patient if hasattr(obj, "_sa_instance_state") and obj.patient else None,
            dentist=obj.dentist if hasattr(obj, "_sa_instance_state") and obj.dentist else None,
            appointment=obj.appointment if hasattr(obj, "_sa_instance_state") and obj.appointment else None,
        )


class PrescriptionSearchResult(BaseModel):
    prescriptions: list[PrescriptionRead]
    total: int
    page: int
    limit: int
    total_pages: int


class DentalRecordBase(BaseModel):
    patient_id: str
    previous_problems: str | None = None
    diagnoses: str | None = None
    treatments: str | None = None
    surgeries: str | None = None
    allergies: str | None = None
    medications: str | None = None
    xrays: list[str] = []
    reports: list[str] = []
    images: list[str] = []
    notes: str | None = None
    follow_up_date: datetime | None = None


class DentalRecordCreate(DentalRecordBase):
    pass


class DentalRecordUpdate(BaseModel):
    previous_problems: str | None = None
    diagnoses: str | None = None
    treatments: str | None = None
    surgeries: str | None = None
    allergies: str | None = None
    medications: str | None = None
    xrays: list[str] | None = None
    reports: list[str] | None = None
    images: list[str] | None = None
    notes: str | None = None
    follow_up_date: datetime | None = None


class DentalRecordRead(BaseModel):
    id: str
    patient_id: str
    dentist_id: str | None
    appointment_id: str | None = None
    previous_problems: str | None
    diagnoses: str | None
    treatments: str | None
    surgeries: str | None
    allergies: str | None
    medications: str | None
    xrays: list[str] = []
    reports: list[str] = []
    images: list[str] = []
    notes: str | None
    follow_up_date: datetime | None = None
    created_at: datetime
    updated_at: datetime
    patient: Optional["UserRead"] = None
    dentist: Optional["DentistRead"] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, obj: "DentalRecord") -> "DentalRecordRead":
        def _split(val: str | None) -> list[str]:
            if not val:
                return []
            return [v.strip() for v in val.split(",") if v.strip()]

        return cls(
            id=obj.id,
            patient_id=obj.patient_id,
            dentist_id=obj.dentist_id,
            appointment_id=obj.appointment_id if hasattr(obj, "appointment_id") else None,
            previous_problems=obj.previous_problems,
            diagnoses=obj.diagnoses,
            treatments=obj.treatments,
            surgeries=obj.surgeries,
            allergies=obj.allergies,
            medications=obj.medications,
            xrays=_split(obj.xrays_path) if hasattr(obj, "xrays_path") else [],
            reports=_split(obj.reports_path) if hasattr(obj, "reports_path") else [],
            images=_split(obj.images_path) if hasattr(obj, "images_path") else [],
            notes=obj.notes,
            follow_up_date=obj.follow_up_date,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            patient=obj.patient if hasattr(obj, "_sa_instance_state") and obj.patient else None,
            dentist=obj.dentist if hasattr(obj, "_sa_instance_state") and obj.dentist else None,
        )


class UserSettingsBase(BaseModel):
    theme: str = "system"
    language: str = "en"
    timezone: str = "UTC"
    email_notifications: bool = True
    sms_notifications: bool = False
    browser_notifications: bool = True
    appointment_reminders: bool = True
    data_sharing: bool = False
    two_factor_enabled: bool = False
    ai_streaming: bool = True
    ai_citations: bool = True
    ai_visual_retrieval: bool = True
    ai_response_style: str = "balanced"


class UserSettingsUpdate(BaseModel):
    theme: str | None = None
    language: str | None = None
    timezone: str | None = None
    email_notifications: bool | None = None
    sms_notifications: bool | None = None
    browser_notifications: bool | None = None
    appointment_reminders: bool | None = None
    data_sharing: bool | None = None
    two_factor_enabled: bool | None = None
    ai_streaming: bool | None = None
    ai_citations: bool | None = None
    ai_visual_retrieval: bool | None = None
    ai_response_style: str | None = None


class UserSettingsRead(UserSettingsBase):
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HelpArticleBase(BaseModel):
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    category: str = Field(min_length=1)
    tags: list[str] = []
    is_published: bool = True
    order: int = 0


class HelpArticleCreate(HelpArticleBase):
    pass


class HelpArticleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    content: str | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, min_length=1)
    tags: list[str] | None = None
    is_published: bool | None = None
    order: int | None = None


class HelpArticleRead(HelpArticleBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HelpCategoryRead(BaseModel):
    category: str
    count: int


class ContactSupportCreate(BaseModel):
    subject: str = Field(min_length=1)
    message: str = Field(min_length=1)
    category: str = Field(min_length=1)


class ContactSupportRead(BaseModel):
    id: str
    user_id: str
    subject: str
    message: str
    category: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackCreateExtended(BaseModel):
    type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    rating: int | None = Field(default=None, ge=1, le=5)


class DentalRecordSearchParams(BaseModel):
    patient_id: str | None = None
    dentist_id: str | None = None
    query: str | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=50)


class DentalRecordSearchResult(BaseModel):
    records: list[DentalRecordRead]
    total: int
    page: int
    limit: int
    total_pages: int


class DashboardStats(BaseModel):
    total_users: int
    total_dentists: int
    total_patients: int
    total_appointments: int
    pending_appointments: int
    completed_appointments: int
    recent_activities: list[dict] = []


class PatientDashboardStats(BaseModel):
    upcoming_appointment: Optional["AppointmentRead"] = None
    last_prescription: Optional["PrescriptionRead"] = None
    recent_prescriptions: list["PrescriptionRead"] = []
    recent_dental_records: list["DentalRecordRead"] = []
    appointment_statistics: dict = {}


class DentistDashboardStats(BaseModel):
    todays_appointments: list["AppointmentRead"] = []
    pending_appointments: list["AppointmentRead"] = []
    recent_prescriptions: list["PrescriptionRead"] = []
    recent_dental_records: list["DentalRecordRead"] = []
    patient_statistics: dict = {}


AppointmentRead.model_rebuild()
PrescriptionRead.model_rebuild()
DentalRecordRead.model_rebuild()
PatientDashboardStats.model_rebuild()
DentistDashboardStats.model_rebuild()


# ── Dentist Scraper Schemas ──────────────────────────────────────────────


class DentistProfileSchema(BaseModel):
    """Schema for a scraped dentist profile."""
    name: str
    slug: str = ""
    profile_id: str = ""
    profile_url: str = ""
    qualifications: str = ""
    degrees: str = ""
    specialty: str = ""
    department: str = "Dentistry"
    hospital: str = "Aga Khan University Hospital"
    experience_years: int = 0
    gender: str = ""
    clinic_name: str = "Aga Khan University Hospital"
    clinic_address: str = ""
    consultation_fee: float = 0.0
    consultation_timings: str = ""
    available_days: str = ""
    appointment_url: str = ""
    languages: list[str] = []
    biography: str = ""
    areas_of_interest: str = ""
    clinical_interests: str = ""
    research_interests: str = ""
    education: str = ""
    certifications: str = ""
    awards: str = ""
    publications: str = ""
    memberships: str = ""
    image_url: str = ""
    image_path: str = ""
    phone: str = ""
    email: str = ""
    hospital_address: str = ""
    content_hash: str = ""
    schedule: list[dict[str, str]] = []


class DentistFullRead(BaseModel):
    """Full dentist read schema with all scraped fields."""
    id: str
    full_name: str
    slug: str | None = None
    qualification: str | None = None
    degrees: str | None = None
    specialization: str = ""
    department: str | None = None
    hospital: str | None = None
    experience_years: int = 0
    gender: str | None = None
    clinic_name: str | None = None
    clinic_address: str | None = None
    clinic_phone: str | None = None
    clinic_email: str | None = None
    consultation_fee: float = 0.0
    consultation_timings: str | None = None
    available_days: str | None = None
    appointment_url: str | None = None
    languages: list[str] = []
    biography: str | None = None
    areas_of_interest: str | None = None
    clinical_interests: str | None = None
    research_interests: str | None = None
    education: str | None = None
    certifications: str | None = None
    awards: str | None = None
    publications: str | None = None
    memberships: str | None = None
    profile_picture: str | None = None
    image_url: str | None = None
    image_path: str | None = None
    profile_url: str | None = None
    phone: str | None = None
    email: str | None = None
    hospital_address: str | None = None
    source_url: str | None = None
    rating: float = 0.0
    total_reviews: int = 0
    is_active: bool = True
    data_version: int = 1
    last_scraped_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DentistSearchParamsV2(BaseModel):
    """Enhanced search parameters for dentist search."""
    query: str | None = None
    specialization: str | None = None
    clinic: str | None = None
    hospital: str | None = None
    min_experience: int | None = Field(default=None, ge=0)
    max_fee: float | None = Field(default=None, ge=0)
    language: str | None = None
    gender: str | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=50)
    sort_by: str = Field(default="name", pattern="^(name|experience|rating|fee)$")
    sort_order: str = Field(default="asc", pattern="^(asc|desc)$")


class DentistSearchResultV2(BaseModel):
    """Paginated dentist search result."""
    dentists: list[DentistFullRead]
    total: int
    page: int
    limit: int
    total_pages: int


class SyncRequest(BaseModel):
    """Request body for dentist sync."""
    force: bool = False


class SyncResultResponse(BaseModel):
    """Response from a sync operation."""
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    images_downloaded: int = 0
    errors: list[str] = []
    elapsed_seconds: float = 0.0
    total_profiles: int = 0


class ExportResponse(BaseModel):
    """Response from export operation."""
    csv_path: str | None = None
    json_path: str | None = None
    total_exported: int = 0


class DentistSpecializationStat(BaseModel):
    """Specialization with count."""
    value: str
    label: str
    count: int


class DentistAvailabilitySlot(BaseModel):
    """Availability slot."""
    day_of_week: int
    start_time: str
    end_time: str
    is_available: bool = True


class ReindexRequest(BaseModel):
    """Request body for reindex operation."""
    pass


class UserPreferencesRead(BaseModel):
    preferred_language: str = "en"
    simplify_for_patient: bool = False
    preferred_specialty: str = ""
    frequently_asked_topics: list[str] = []
    recent_sessions: list[dict[str, str]] = []


class UserPreferencesUpdate(BaseModel):
    preferred_language: str | None = None
    simplify_for_patient: bool | None = None
    preferred_specialty: str | None = None


class EvaluationMetricsResponse(BaseModel):
    total_queries: int = 0
    avg_retrieval_latency_ms: float = 0.0
    avg_llm_latency_ms: float = 0.0
    citation_accuracy: float = 0.0
    user_satisfaction: float = 0.0
    hallucination_rate: float = 0.0
    failed_retrievals: int = 0
    mode_breakdown: dict[str, int] = {}
