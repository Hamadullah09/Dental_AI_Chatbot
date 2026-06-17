import type { AuthResponse, ChatResponse, ChatSession, DocumentItem, UserRole } from "./types";

type ApiOptions = RequestInit & {
  token?: string | null;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function isInvalidTokenError(error: unknown) {
  return error instanceof ApiError && error.status === 401;
}

async function request<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  const response = await fetch(`/api${path}`, {
    ...options,
    headers
  });

  const contentType = response.headers.get("content-type") || "";
  const data = response.status === 204
    ? null
    : contentType.includes("application/json")
      ? await response.json()
      : await response.text();
  if (!response.ok) {
    throw new ApiError(typeof data === "string" ? data : data?.detail || "Request failed", response.status);
  }
  return data as T;
}

export function register(input: {
  email: string;
  password: string;
  full_name?: string;
  role: UserRole;
}) {
  return request<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export function login(input: { email: string; password: string }) {
  return request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export function sendChat(input: { question: string; session_id?: string | null }, token: string) {
  return request<ChatResponse>("/chat", {
    method: "POST",
    token,
    body: JSON.stringify(input)
  });
}

export function getSessions(token: string) {
  return request<ChatSession[]>("/chat/sessions", { token });
}

export function sendFeedback(input: { message_id: string; rating: number; comment?: string }, token: string) {
  return request("/feedback", {
    method: "POST",
    token,
    body: JSON.stringify(input)
  });
}

export function getDocuments(token: string) {
  return request<DocumentItem[]>("/admin/documents", { token });
}

export type UploadDocumentMetadata = {
  book_title?: string;
  author_or_source?: string;
  year?: string;
  edition?: string;
  document_type?: string;
  trust_level?: string;
  specialty?: string;
  language?: string;
  review_status?: string;
};

export function uploadDocument(file: File, token: string, metadata: UploadDocumentMetadata = {}) {
  const form = new FormData();
  form.append("file", file);
  Object.entries(metadata).forEach(([key, value]) => {
    const trimmed = String(value || "").trim();
    if (trimmed) {
      form.append(key, trimmed);
    }
  });
  return request<DocumentItem>("/admin/documents", {
    method: "POST",
    token,
    body: form
  });
}

export function reingestDocument(documentId: string, token: string) {
  return request<DocumentItem>(`/admin/documents/${documentId}/reingest`, {
    method: "POST",
    token
  });
}

export function deleteDocument(documentId: string, token: string) {
  return request(`/admin/documents/${documentId}`, {
    method: "DELETE",
    token
  });
}
