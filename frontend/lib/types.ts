export type UserRole = "admin" | "dentist" | "student" | "patient";

export type User = {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  created_at: string;
};

export type AuthResponse = {
  access_token: string;
  refresh_token?: string | null;
  token_type: "bearer";
  user: User;
};

export type SourceCitation = {
  source_type?: "pdf" | "web" | string;
  document_id: string | null;
  document_name: string;
  page_number: number | null;
  chunk_index: number | null;
  url?: string | null;
  score: number | null;
};

export type VisualCitation = {
  visual_id: string;
  document_id: string | null;
  document_name: string;
  page_number: number | null;
  visual_type: "figure" | "diagram" | "chart" | "flowchart" | "table" | "page_snapshot" | "unknown" | string;
  image_path: string;
  image_url: string;
  caption_text?: string | null;
  generated_description?: string | null;
  score: number | null;
};

export type ChatResponse = {
  answer: string;
  session_id: string;
  message_id: string;
  sources: SourceCitation[];
  visuals: VisualCitation[];
  answer_mode: "rag_grounded" | "general_fallback" | "insufficient_evidence" | "web_augmented" | "conversational" | string;
  disclaimer: string;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: SourceCitation[];
  visuals?: VisualCitation[];
  created_at: string;
};

export type ChatSession = {
  id: string;
  title: string | null;
  archived?: boolean;
  created_at: string;
  updated_at: string;
  messages: Message[];
};

export type DocumentItem = {
  id: string;
  filename: string;
  original_filename: string;
  title: string | null;
  author_or_source: string | null;
  edition: string | null;
  publication_year: number | null;
  document_type: "guideline" | "textbook" | "patient_education" | "research_article" | "other";
  trust_level: "high" | "medium" | "low";
  review_status: "unreviewed" | "reviewed" | "approved" | "rejected";
  specialty: string | null;
  language: string | null;
  file_hash: string | null;
  status: "uploaded" | "processing" | "ready" | "failed";
  chunk_count: number;
  error_message: string | null;
  ingestion_progress: number;
  ingestion_step: string | null;
  ocr_used: boolean;
  ingestion_started_at: string | null;
  ingestion_completed_at: string | null;
  created_at: string;
};

export type DocumentIngestionLog = {
  id: string;
  document_id: string;
  level: "info" | "warning" | "error" | string;
  message: string;
  created_at: string;
};

export type DatasetGenerationStatus = {
  state: "idle" | "queued" | "running" | "completed" | "failed" | string;
  processed_chunks: number;
  generated_items: number;
  skipped_chunks: number;
  duplicate_chunks: number;
  removed_existing_rows: number;
  document_id?: string | null;
  document_name?: string | null;
  output_path: string;
  skipped_path: string;
  review_csv_path?: string | null;
  provider?: string | null;
  message: string | null;
  updated_at?: string | null;
};

export type DentistSpecialization =
  | "general"
  | "orthodontics"
  | "periodontics"
  | "endodontics"
  | "prosthodontics"
  | "oral_surgery"
  | "pediatric"
  | "cosmetic"
  | "implantology";

export type Dentist = {
  id: string;
  full_name: string;
  qualification: string | null;
  specialization: DentistSpecialization[];
  experience_years: number | null;
  clinic_name: string | null;
  consultation_fee: number | null;
  available_timings: TimeSlot[];
  languages: string[];
  biography: string | null;
  profile_picture_url: string | null;
  is_available: boolean;
  source_url: string | null;
  created_at: string;
  updated_at: string;
};

export type TimeSlot = {
  day_of_week: number;
  start_time: string;
  end_time: string;
  is_available: boolean;
};

export type AppointmentStatus =
  | "pending"
  | "confirmed"
  | "completed"
  | "cancelled"
  | "rejected"
  | "no_show";

export type Appointment = {
  id: string;
  patient_id: string;
  dentist_id: string;
  appointment_date: string;
  duration_minutes: number;
  status: AppointmentStatus;
  notes: string | null;
  reason: string | null;
  rejection_reason: string | null;
  created_at: string;
  updated_at: string;
  patient?: User | null;
  dentist?: Dentist | null;
};

export type Prescription = {
  id: string;
  patient_id: string;
  dentist_id: string;
  appointment_id: string;
  diagnosis: string;
  medicines: string;
  dosage: string;
  frequency: string;
  duration: string;
  instructions: string | null;
  notes: string | null;
  follow_up_date: string | null;
  attachments: string[];
  created_at: string;
  updated_at: string;
  patient?: User | null;
  dentist?: Dentist | null;
  appointment?: Appointment | null;
};

export type DentalRecord = {
  id: string;
  patient_id: string;
  dentist_id: string;
  previous_problems: string | null;
  diagnoses: string | null;
  treatments: string | null;
  surgeries: string | null;
  allergies: string | null;
  medications: string | null;
  xrays: string[];
  reports: string[];
  images: string[];
  notes: string | null;
  follow_up_records: string | null;
  created_at: string;
  updated_at: string;
  patient?: User | null;
  dentist?: Dentist | null;
};

export type UserSettings = {
  theme: string;
  language: string;
  timezone: string;
  email_notifications: boolean;
  push_notifications: boolean;
  chat_history_retention_days: number;
  data_sharing_consent: boolean;
  hipaa_consent: boolean;
  ai_disclaimer_acknowledged: boolean;
};

export type HelpArticle = {
  id: string;
  title: string;
  content: string;
  category: string;
  tags: string[];
  is_published: boolean;
  view_count: number;
  helpful_count: number;
  created_at: string;
  updated_at: string;
};

export type SupportTicket = {
  id: string;
  user_id: string;
  subject: string;
  message: string;
  category: string;
  priority: string;
  status: string;
  admin_response: string | null;
  created_at: string;
  updated_at: string;
};
