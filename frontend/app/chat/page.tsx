"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { SendHorizonal, Sparkles } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { ChatMessage } from "@/components/ChatMessage";
import { sendChat } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Message } from "@/lib/types";

export default function ChatPage() {
  const { token } = useAuth();
  const [question, setQuestion] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [status, setStatus] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !question.trim()) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: question.trim(),
      sources: [],
      created_at: new Date().toISOString()
    };

    setMessages((current) => [...current, userMessage]);
    setQuestion("");
    setIsLoading(true);
    setStatus("Retrieving dental context...");

    try {
      const response = await sendChat({ question: userMessage.content, session_id: sessionId }, token);
      setSessionId(response.session_id);
      setMessages((current) => [
        ...current,
        {
          id: response.message_id,
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          created_at: new Date().toISOString()
        }
      ]);
      setStatus(response.disclaimer);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Chat request failed");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <AuthGate>
      <AppShell title="Dental Chat" subtitle="Ask questions grounded in uploaded dental PDFs.">
        <section className="chat-layout">
          <div className="messages">
            {messages.length === 0 ? (
              <div className="empty-state">
                <div>
                  <Sparkles size={34} />
                  <h2>How can Dental AI help?</h2>
                  <p>Ask about prevention, oral pathology, restorative dentistry, periodontal care, or uploaded clinical references.</p>
                </div>
              </div>
            ) : (
              messages.map((message) => (
                <ChatMessage key={message.id} message={message} onStatus={setStatus} />
              ))
            )}
            <div ref={bottomRef} />
          </div>

          <form className="composer-wrap" onSubmit={onSubmit}>
            <div className="composer">
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Message Dental AI..."
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
              />
              <button className="icon-button" disabled={isLoading || !question.trim()} aria-label="Send message">
                <SendHorizonal size={18} />
              </button>
            </div>
            <p className="status" style={{ width: "min(860px, 100%)", margin: "10px auto 0" }}>{status}</p>
          </form>
        </section>
      </AppShell>
    </AuthGate>
  );
}
