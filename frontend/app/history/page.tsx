"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { ChatMessage } from "@/components/ChatMessage";
import { getSessions } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ChatSession } from "@/lib/types";

export default function HistoryPage() {
  const { token } = useAuth();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (!token) return;
    getSessions(token)
      .then((data) => {
        setSessions(data);
        setActiveSession(data[0] || null);
      })
      .catch((error) => setStatus(error instanceof Error ? error.message : "Could not load history"));
  }, [token]);

  return (
    <AuthGate>
      <AppShell title="Chat History" subtitle="Review previous dental conversations and citations.">
        <div className="content two-column">
          <section className="panel">
            <h2>Sessions</h2>
            <div className="list">
              {sessions.length ? sessions.map((session) => (
                <button
                  className="list-item"
                  key={session.id}
                  onClick={() => setActiveSession(session)}
                  style={{ textAlign: "left", color: "var(--text)" }}
                >
                  <strong>{session.title || "Untitled chat"}</strong>
                  <span className="muted">{new Date(session.updated_at).toLocaleString()}</span>
                </button>
              )) : <p className="muted">No saved conversations yet.</p>}
            </div>
          </section>

          <section className="panel">
            <h2>{activeSession?.title || "Conversation"}</h2>
            <div className="list">
              {activeSession?.messages.length ? activeSession.messages.map((message) => (
                <ChatMessage key={message.id} message={message} onStatus={setStatus} />
              )) : <p className="muted">Select a session to inspect its messages.</p>}
            </div>
            <p className="status">{status}</p>
          </section>
        </div>
      </AppShell>
    </AuthGate>
  );
}
