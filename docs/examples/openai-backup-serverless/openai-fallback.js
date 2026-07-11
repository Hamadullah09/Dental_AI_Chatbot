const OPENAI_API_URL = "https://api.openai.com/v1/chat/completions";

function corsHeaders(origin) {
  const allowedOrigin = process.env.ALLOWED_ORIGIN || origin || "*";
  return {
    "Access-Control-Allow-Origin": allowedOrigin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
  };
}

function prompt(question) {
  return [
    "You are Dental AI backup mode.",
    "Give general dental education from your own knowledge.",
    "Do not claim this is based on uploaded documents.",
    "Do not invent citations, page numbers, or source names.",
    "Do not diagnose or prescribe medicine.",
    "Recommend a licensed dentist for symptoms or treatment decisions.",
    "",
    `User question: ${question}`,
    "",
    "Answer format:",
    "General dental guidance, not from uploaded documents:",
    "",
    "Direct Answer:",
    "Explanation:",
    "Safety Note:",
  ].join("\n");
}

module.exports = async function handler(req, res) {
  const headers = corsHeaders(req.headers.origin);
  Object.entries(headers).forEach(([key, value]) => res.setHeader(key, value));

  if (req.method === "OPTIONS") {
    res.status(204).end();
    return;
  }
  if (req.method !== "POST") {
    res.status(405).json({ detail: "Method not allowed" });
    return;
  }

  const question = String(req.body?.question || "").trim();
  if (!question) {
    res.status(400).json({ detail: "Question is required." });
    return;
  }

  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    res.status(503).json({ detail: "OpenAI backup is not configured." });
    return;
  }

  try {
    const response = await fetch(OPENAI_API_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: process.env.OPENAI_MODEL || "gpt-4o-mini",
        temperature: 0.2,
        max_tokens: 650,
        messages: [
          {
            role: "system",
            content: "You are Dental AI backup mode. Provide safe general dental education only. Never invent citations.",
          },
          { role: "user", content: prompt(question) },
        ],
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      res.status(response.status).json({ detail: data?.error?.message || "OpenAI backup request failed." });
      return;
    }

    res.status(200).json({
      answer: String(data?.choices?.[0]?.message?.content || "").trim(),
      session_id: req.body?.session_id || "",
      message_id: `openai-backup-${Date.now()}`,
      sources: [],
      answer_mode: "openai_backup",
      disclaimer:
        "Primary Dental AI backend was unavailable, so this is general dental guidance from independent OpenAI backup mode. It is not based on uploaded documents.",
    });
  } catch (error) {
    res.status(502).json({ detail: "OpenAI backup could not be reached." });
  }
};
