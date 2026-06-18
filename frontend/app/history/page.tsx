"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { MessageBubble } from "@/components/MessageBubble";
import { getSessions } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ChatSession } from "@/lib/types";
import { Calendar, MessageSquare, BookOpen } from "lucide-react";

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
        <div className="flex-1 flex flex-col md:flex-row gap-6 p-4 md:p-8 overflow-hidden h-full min-h-0 bg-dental-darkBg text-white">
          
          {/* Left panel: List of sessions */}
          <section className="w-full md:w-80 bg-dental-card border border-dental-border rounded-2xl p-4 flex flex-col min-h-0">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-dental-accent mb-3 flex items-center gap-2">
              <MessageSquare size={16} /> Saved Consultations
            </h2>
            <div className="flex-1 overflow-y-auto space-y-2 pr-1">
              {sessions.length ? (
                sessions.map((session) => (
                  <button
                    className={`w-full p-3 rounded-xl border text-left transition-all ${
                      activeSession?.id === session.id
                        ? "bg-dental-border border-dental-accent text-white"
                        : "bg-dental-darkBg/60 border-dental-border hover:bg-dental-border/50 text-gray-300"
                    }`}
                    key={session.id}
                    onClick={() => setActiveSession(session)}
                  >
                    <strong className="block text-xs font-semibold truncate mb-1">{session.title || "Untitled chat"}</strong>
                    <span className="flex items-center gap-1 text-[10px] text-gray-500 font-medium">
                      <Calendar size={10} />
                      {new Date(session.updated_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}
                    </span>
                  </button>
                ))
              ) : (
                <p className="text-xs text-gray-500 italic p-2 text-center mt-6">No saved conversations yet.</p>
              )}
            </div>
          </section>

          {/* Right panel: Active session message history */}
          <section className="flex-1 bg-dental-card border border-dental-border rounded-2xl p-6 flex flex-col min-h-0 relative">
            {activeSession ? (
              <>
                <div className="border-b border-dental-border pb-3 mb-4 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <BookOpen size={16} className="text-dental-accent" />
                    <h2 className="text-sm font-bold text-white truncate max-w-md">{activeSession.title || "Untitled consultation"}</h2>
                  </div>
                  <span className="text-[10px] text-gray-500">
                    ID: {activeSession.id.substring(0, 8)}...
                  </span>
                </div>

                <div className="flex-1 overflow-y-auto space-y-6 pr-1">
                  {activeSession.messages.length ? (
                    activeSession.messages.map((message) => (
                      <MessageBubble 
                        key={message.id} 
                        message={message} 
                        onStatus={setStatus} 
                      />
                    ))
                  ) : (
                    <p className="text-xs text-gray-500 italic text-center mt-12">No messages in this session.</p>
                  )}
                </div>
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-6">
                <MessageSquare className="w-12 h-12 text-gray-600 mb-3" />
                <p className="text-sm text-gray-400 font-medium">Select a saved consultation session from the list to review the conversation log and clinical sources.</p>
              </div>
            )}

            {/* Error / Status Bar */}
            {status && (
              <div className="absolute top-2 left-1/2 -translate-x-1/2 px-4 py-1.5 bg-dental-card border border-dental-border rounded-full text-[10px] text-dental-textSecondary max-w-md text-center shadow-lg pointer-events-none z-20">
                {status}
              </div>
            )}
          </section>
        </div>
      </AppShell>
    </AuthGate>
  );
}
