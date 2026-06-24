"use client";

import React, { useState } from "react";
import { useAuth } from "@/lib/auth";
import { Stethoscope, FileText, ThumbsUp, ThumbsDown, Globe2 } from "lucide-react";
import type { Message } from "@/lib/types";
import { sendFeedback } from "@/lib/api";

interface MessageBubbleProps {
  message: Message;
  onStatus?: (status: string) => void;
}

export function MessageBubble({ message, onStatus }: MessageBubbleProps) {
  const { token, user } = useAuth();
  const [feedbackGiven, setFeedbackGiven] = useState<"helpful" | "needs-work" | null>(null);
  const isAssistant = message.role === "assistant";

  const initials = user?.full_name
    ? user.full_name.split(" ").map((n) => n[0]).join("").toUpperCase().substring(0, 2)
    : user?.email ? user.email.substring(0, 2).toUpperCase() : "JD";

  async function handleFeedback(rating: number, type: "helpful" | "needs-work") {
    if (!token || !message.id) return;
    try {
      await sendFeedback({ message_id: message.id, rating }, token);
      setFeedbackGiven(type);
      onStatus?.("Thank you for your feedback!");
      setTimeout(() => onStatus?.(""), 3000);
    } catch (error) {
      onStatus?.(error instanceof Error ? error.message : "Feedback failed");
    }
  }

  const formatContent = (text: string) => {
    return text.split("\n").map((line, idx) => {
      let formattedLine = line;

      // Handle bold syntax: **text**
      const boldRegex = /\*\*(.*?)\*\*/g;
      const parts: React.ReactNode[] = [];
      let lastIndex = 0;
      let match;
      
      while ((match = boldRegex.exec(formattedLine)) !== null) {
        if (match.index > lastIndex) {
          parts.push(formattedLine.substring(lastIndex, match.index));
        }
        parts.push(<strong key={match.index} className="font-semibold text-dental-textPrimary">{match[1]}</strong>);
        lastIndex = boldRegex.lastIndex;
      }
      if (lastIndex < formattedLine.length) {
        parts.push(formattedLine.substring(lastIndex));
      }

      const contentElements = parts.length > 0 ? parts : formattedLine;

      if (line.trim().startsWith("• ") || line.trim().startsWith("- ") || line.trim().startsWith("* ")) {
        const cleanText = line.trim().substring(2);
        return (
          <li key={idx} className="ml-4 list-disc text-sm text-dental-textPrimary mt-1 leading-relaxed">
            {parts.length > 0 ? parts : cleanText}
          </li>
        );
      }

      return (
        <p key={idx} className="text-sm text-dental-textPrimary leading-relaxed mb-2 break-words">
          {contentElements}
        </p>
      );
    });
  };

  return (
    <article className={`flex gap-4 ${message.role === "user" ? "flex-row-reverse" : "flex-row"} fade-in w-full`}>
      {/* Avatar */}
      <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 shadow-sm ${
        isAssistant 
          ? "bg-dental-card border border-dental-border text-dental-accent" 
          : "bg-gradient-to-br from-dental-accent to-blue-600 text-white text-xs font-bold"
      }`}>
        {isAssistant ? <Stethoscope size={15} /> : initials}
      </div>

      {/* Bubble Content */}
      <div className="max-w-[85%] md:max-w-[75%] flex flex-col gap-1">
        <div className={`px-4 py-3 text-sm leading-relaxed rounded-2xl shadow-sm ${
          message.role === "user"
            ? "bg-dental-accent text-white rounded-tr-sm"
            : "bg-dental-card border border-dental-border text-dental-textPrimary rounded-tl-sm"
        }`}>
          {/* Main Text */}
          {isAssistant ? (
            <div>{formatContent(message.content)}</div>
          ) : (
            <div className="whitespace-pre-wrap">{message.content}</div>
          )}

          {/* Render Sources if Assistant */}
          {isAssistant && message.sources && message.sources.length > 0 && (
            <div className="mt-3 pt-3 border-t border-dental-border/40">
              <p className="text-[11px] font-semibold text-dental-accent uppercase tracking-wider mb-1.5 flex items-center gap-1">
                <FileText size={11} /> Grounded Sources:
              </p>
              <div className="flex flex-wrap gap-1.5">
                {message.sources.map((source, index) => (
                  source.source_type === "web" && source.url ? (
                    <a
                      key={index}
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-dental-darkBg border border-dental-border text-[10px] text-dental-textSecondary hover:text-dental-textPrimary transition-colors"
                      title={source.url}
                    >
                      <Globe2 size={10} className="text-sky-400 shrink-0" />
                      <span className="max-w-[150px] truncate">{source.document_name}</span>
                    </a>
                  ) : (
                    <span
                      key={index}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-dental-darkBg border border-dental-border text-[10px] text-dental-textSecondary hover:text-dental-textPrimary transition-colors"
                      title={`Source chunk: ${source.chunk_index}, confidence score: ${source.score ? (source.score * 100).toFixed(0) : "N/A"}%`}
                    >
                      <FileText size={10} className="text-teal-500 shrink-0" />
                      <span className="max-w-[120px] truncate">{source.document_name}</span>
                      {source.page_number && <span className="opacity-60">p.{source.page_number}</span>}
                    </span>
                  )
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Timestamp and Feedback bar */}
        <div className="flex items-center justify-between px-1">
          <span className="text-[10px] text-dental-textSecondary">
            {message.created_at ? new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>

          {/* Feedback buttons for assistant message */}
          {isAssistant && message.id && (
            <div className="flex items-center gap-2">
              <button 
                type="button"
                onClick={() => handleFeedback(5, "helpful")}
                disabled={feedbackGiven !== null}
                className={`p-1.5 rounded-lg hover:bg-white/5 transition-all ${
                  feedbackGiven === "helpful" ? "text-dental-accent" : "text-dental-textSecondary hover:text-dental-textPrimary"
                }`}
                title="Helpful response"
              >
                <ThumbsUp size={12} />
              </button>
              <button 
                type="button"
                onClick={() => handleFeedback(1, "needs-work")}
                disabled={feedbackGiven !== null}
                className={`p-1.5 rounded-lg hover:bg-white/5 transition-all ${
                  feedbackGiven === "needs-work" ? "text-red-400" : "text-dental-textSecondary hover:text-dental-textPrimary"
                }`}
                title="Needs improvements"
              >
                <ThumbsDown size={12} />
              </button>
            </div>
          )}
        </div>
      </div>
    </article>
  );
}
