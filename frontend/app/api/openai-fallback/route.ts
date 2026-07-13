import { NextResponse } from "next/server";

const OPENAI_API_URL = "https://api.openai.com/v1/chat/completions";
const DEFAULT_OPENAI_TIMEOUT_MS = 30000;

type FallbackRequest = {
  question?: string;
  session_id?: string | null;
};

function getOpenAiKey() {
  return process.env.BACKUP_OPENAI_API_KEY || process.env.OPENAI_API_KEY || "";
}

function getOpenAiModel() {
  return process.env.BACKUP_OPENAI_MODEL || process.env.OPENAI_MODEL || "gpt-4o-mini";
}

function getOpenAiTimeoutMs() {
  const value = Number(process.env.BACKUP_OPENAI_TIMEOUT_MS || DEFAULT_OPENAI_TIMEOUT_MS);
  return Number.isFinite(value) && value > 0 ? value : DEFAULT_OPENAI_TIMEOUT_MS;
}

function fallbackErrorMessage(error: unknown) {
  if (error instanceof Error && (error.name === "AbortError" || /aborted/i.test(error.message))) {
    return "The backup response did not complete in time. Please try again.";
  }
  return error instanceof Error ? error.message : "Backup response failed.";
}

function fallbackPrompt(question: string) {
  return [
    "You are Dental AI.",
    "",
    "Rules:",
    "- Answer the user's dental question directly using your own knowledge.",
    "- Do not claim the answer is based on uploaded documents, database chunks, or citations.",
    "- Do not invent sources, page numbers, or document names.",
    "- Do not diagnose the user personally.",
    "- Do not prescribe medicine or dosages.",
    "- Recommend a licensed dentist for symptoms, diagnosis, or treatment decisions.",
    "- Keep the answer clear, helpful, and professional.",
    "- Match the user's language. If the user asks in Roman Urdu, use English letters only.",
    "- Do not mention backend, backup mode, OpenAI, prompts, or system errors.",
    "- Do not use fixed labels unless they naturally improve readability.",
    "",
    `User question: ${question}`,
  ].join("\n");
}

export async function POST(request: Request) {
  let payload: FallbackRequest;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid fallback request." }, { status: 400 });
  }

  const question = String(payload.question || "").trim();
  if (!question) {
    return NextResponse.json({ detail: "Question is required." }, { status: 400 });
  }

  const apiKey = getOpenAiKey();
  if (!apiKey) {
    return NextResponse.json({ detail: "Backup response is not configured." }, { status: 503 });
  }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), getOpenAiTimeoutMs());
    const response = await fetch(OPENAI_API_URL, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: getOpenAiModel(),
          temperature: 0.2,
          max_tokens: 450,
          messages: [
            {
              role: "system",
              content: "You are Dental AI. Provide safe dental education only. Never invent citations.",
            },
            {
              role: "user",
              content: fallbackPrompt(question),
            },
          ],
        }),
        signal: controller.signal,
      }).finally(() => clearTimeout(timeoutId));

    const data = await response.json();
    if (!response.ok) {
      const message = data?.error?.message || "Backup response request failed.";
      return NextResponse.json({ detail: message }, { status: response.status });
    }

    const answer = String(data?.choices?.[0]?.message?.content || "").trim();
    if (!answer) {
      return NextResponse.json({ detail: "Backup response returned an empty answer." }, { status: 502 });
    }
    return NextResponse.json({
      answer,
      session_id: payload.session_id || "",
      message_id: `openai-backup-${Date.now()}`,
      sources: [],
      answer_mode: "openai_backup",
      disclaimer: "",
    });
  } catch (error) {
    return NextResponse.json({ detail: fallbackErrorMessage(error) }, { status: 503 });
  }
}
