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
  document_id: string | null;
  document_name: string;
  page_number: number | null;
  chunk_index: number | null;
  score: number | null;
};

export type ChatResponse = {
  answer: string;
  session_id: string;
  message_id: string;
  sources: SourceCitation[];
  disclaimer: string;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: SourceCitation[];
  created_at: string;
};

export type ChatSession = {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  messages: Message[];
};

export type DocumentItem = {
  id: string;
  filename: string;
  original_filename: string;
  status: "uploaded" | "processing" | "ready" | "failed";
  chunk_count: number;
  error_message: string | null;
  created_at: string;
};
