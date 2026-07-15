import type { AuthResponse, ChatResponse, ChatSession, DatasetGenerationStatus, DocumentIngestionLog, DocumentItem, User, UserRole } from "./types";

type ApiOptions = RequestInit & {
  token?: string | null;
  timeoutMs?: number;
};

const CHAT_GENERATION_TIMEOUT_MS = Number(
  process.env.NEXT_PUBLIC_CHAT_GENERATION_TIMEOUT_MS || process.env.NEXT_PUBLIC_CHAT_BACKEND_TIMEOUT_MS || 300000
);
const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

function getApiBaseUrl() {
  return API_BASE_URL;
}

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

function clearStaleAuth(path: string, detail: unknown) {
  if (typeof window === "undefined" || path.startsWith("/auth/")) return;
  const message = typeof detail === "string" ? detail : String((detail as { detail?: unknown } | null)?.detail || "");
  const normalized = message.toLowerCase();
  if (!normalized.includes("invalid token") && !normalized.includes("authentication required")) return;

  localStorage.removeItem("dental_ai_token");
  localStorage.removeItem("dental_ai_user");
  window.dispatchEvent(new Event("dental_ai_auth_expired"));
  window.location.replace("/login");
}

async function request<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { token, timeoutMs, ...fetchOptions } = options;
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  let timeoutId: number | null = null;
  const requestPromise = fetch(`${getApiBaseUrl()}/api${path}`, {
    ...fetchOptions,
    headers,
    signal: fetchOptions.signal
  });
  const timeoutPromise = timeoutMs
    ? new Promise<Response>((_, reject) => {
      timeoutId = window.setTimeout(
        () => reject(new ApiError("Dental AI backend did not respond quickly enough.", 0)),
        timeoutMs
      );
    })
    : null;

  let response: Response;
  try {
    response = await (timeoutPromise ? Promise.race([requestPromise, timeoutPromise]) : requestPromise);
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      error instanceof Error ? `Could not reach the Dental AI backend: ${error.message}` : "Could not reach the Dental AI backend.",
      0
    );
  } finally {
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }
  }

  const contentType = response.headers.get("content-type") || "";
  const data = response.status === 204
    ? null
    : contentType.includes("application/json")
      ? await response.json()
      : await response.text();
  if (!response.ok) {
    clearStaleAuth(path, data);
    throw new ApiError(
      response.status === 401 && !path.startsWith("/auth/")
        ? "Session expired. Please sign in again."
        : typeof data === "string" ? data : data?.detail || "Request failed",
      response.status
    );
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

export function getCurrentUser(token: string) {
  return request<User>("/auth/me", { token });
}

export async function sendChat(input: {
  question: string;
  session_id?: string | null;
  document_id?: string | null;
  search_web?: boolean;
}, token: string) {
  return request<ChatResponse>("/chat", {
    method: "POST",
    token,
    timeoutMs: CHAT_GENERATION_TIMEOUT_MS,
    body: JSON.stringify(input)
  });
}

export async function* sendChatStream(input: {
  question: string;
  session_id?: string | null;
  document_id?: string | null;
  search_web?: boolean;
}, token: string): AsyncGenerator<{type: string; [key: string]: any}, void> {
  const headers = new Headers();
  headers.set("Authorization", `Bearer ${token}`);
  headers.set("Content-Type", "application/json");

  const response = await fetch(`${getApiBaseUrl()}/api/chat/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(input),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new ApiError(data?.detail || "Stream request failed", response.status);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new ApiError("Stream not available", 0);

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6);
        if (data === "[DONE]") return;
        try {
          const parsed = JSON.parse(data);
          yield parsed;
        } catch {}
      }
    }
  }
}

export function uploadChatDocument(file: File, token: string) {
  const form = new FormData();
  form.append("file", file);
  form.append("book_title", file.name.replace(/\.[^.]+$/, ""));
  return request<DocumentItem>("/chat/documents", {
    method: "POST",
    token,
    body: form
  });
}

export function getChatDocument(documentId: string, token: string) {
  return request<DocumentItem>(`/chat/documents/${documentId}`, { token });
}

export function getSessions(token: string) {
  return request<ChatSession[]>("/chat/sessions", { token });
}

export function archiveSession(sessionId: string, token: string) {
  return request<void>(`/chat/sessions/${sessionId}/archive`, {
    method: "POST",
    token
  });
}

export function deleteSession(sessionId: string, token: string) {
  return request<void>(`/chat/sessions/${sessionId}`, {
    method: "DELETE",
    token
  });
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

export function getDocumentIngestionLogs(documentId: string, token: string) {
  return request<DocumentIngestionLog[]>(`/admin/documents/${documentId}/logs`, { token });
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

export function getDatasetGenerationStatus(token: string) {
  return request<DatasetGenerationStatus>("/admin/dataset/status", { token });
}

export function generateDataset(token: string, input: {
  document_id?: string | null;
  limit?: number;
  examples_per_chunk?: number;
  min_quality?: number;
  include_noisy?: boolean;
}) {
  return request<DatasetGenerationStatus>("/admin/dataset/generate", {
    method: "POST",
    token,
    body: JSON.stringify(input)
  });
}

export async function downloadDatasetReviewCsv(token: string) {
  const response = await fetch(`${getApiBaseUrl()}/api/admin/dataset/download`, {
    headers: {
      Authorization: `Bearer ${token}`
    }
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new ApiError(detail || "Dataset download failed", response.status);
  }
  return response.blob();
}
