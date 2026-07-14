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
