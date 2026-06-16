"use client";

import { Bot, FileText, UserRound } from "lucide-react";
import { sendFeedback } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Message, SourceCitation } from "@/lib/types";

export function ChatMessage({ message, onStatus }: {
  message: Message;
  onStatus?: (status: string) => void;
}) {
  const { token } = useAuth();
  const isAssistant = message.role === "assistant";

  async function feedback(rating: number) {
    if (!token || !message.id) return;
    try {
      await sendFeedback({ message_id: message.id, rating }, token);
      onStatus?.("Feedback saved.");
    } catch (error) {
      onStatus?.(error instanceof Error ? error.message : "Feedback failed");
    }
  }

  return (
    <article className="message-row">
      <div className="avatar">
        {isAssistant ? <Bot size={18} /> : <UserRound size={18} />}
      </div>
      <div className="message-body">
        {message.content}
        {isAssistant && message.sources?.length ? (
          <SourceList sources={message.sources} />
        ) : null}
        {isAssistant && message.id ? (
          <div className="inline-actions" style={{ marginTop: 12 }}>
            <button className="button secondary" onClick={() => feedback(5)}>Helpful</button>
            <button className="button secondary" onClick={() => feedback(1)}>Needs work</button>
          </div>
        ) : null}
      </div>
    </article>
  );
}

export function SourceList({ sources }: { sources: SourceCitation[] }) {
  return (
    <div className="sources">
      {sources.map((source, index) => (
        <span className="source-pill" key={`${source.document_id}-${source.chunk_index}-${index}`}>
          <FileText size={14} />
          {source.document_name}
          {source.page_number ? ` p.${source.page_number}` : ""}
        </span>
      ))}
    </div>
  );
}
