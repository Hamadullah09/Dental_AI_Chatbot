"use client";

import React, { useState } from "react";
import { useAuth } from "@/lib/auth";
import { BookOpen, Copy, FileText, Globe2, MoreHorizontal, RotateCcw, Share2, ThumbsDown, ThumbsUp, Volume2 } from "lucide-react";
import type { Message } from "@/lib/types";
import { sendFeedback } from "@/lib/api";

interface MessageBubbleProps {
  message: Message;
  onStatus?: (status: string) => void;
}

export function MessageBubble({ message, onStatus }: MessageBubbleProps) {
  const { token } = useAuth();
  const [feedbackGiven, setFeedbackGiven] = useState<"helpful" | "needs-work" | null>(null);
  const [showSources, setShowSources] = useState(false);
  const [showMore, setShowMore] = useState(false);
  const isAssistant = message.role === "assistant";

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

  async function handleCopy() {
    await navigator.clipboard?.writeText(message.content);
    onStatus?.("Copied response.");
    setTimeout(() => onStatus?.(""), 2000);
  }

  async function handleShare() {
    if (navigator.share) {
      await navigator.share({ title: "Dental AI response", text: message.content });
      return;
    }
    await handleCopy();
  }

  function handleRetry() {
    onStatus?.("Retry from the composer by sending the question again.");
    setTimeout(() => onStatus?.(""), 3000);
  }

  const formatContent = (text: string) => {
    return text.split("\n").map((line, idx) => {
      const formattedLine = line;

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
          <li key={idx} className="ml-5 list-disc text-[15px] text-dental-textPrimary mt-1.5 leading-7">
            {parts.length > 0 ? parts : cleanText}
          </li>
        );
      }

      return (
        <p key={idx} className="text-[15px] text-dental-textPrimary leading-7 mb-3 break-words last:mb-0">
          {contentElements}
        </p>
      );
    });
  };

  return (
    <article className={`fade-in w-full py-4 ${message.role === "user" ? "flex justify-end" : "flex justify-start"}`}>
      <div className={`${isAssistant ? "w-full max-w-3xl" : "max-w-[88%] sm:max-w-[72%]"}`}>
        {/* Bubble Content */}
        <div className={`flex min-w-0 flex-1 flex-col gap-2 ${isAssistant ? "" : "items-end"}`}>
          <div className={`max-w-full text-sm leading-relaxed ${
            message.role === "user"
              ? "rounded-[1.65rem] bg-[#2f2f2f] px-5 py-3 text-white shadow-sm"
              : "w-full px-1 py-1 text-dental-textPrimary"
          }`}>
          {/* Main Text */}
          {isAssistant ? (
            <div>{formatContent(message.content)}</div>
          ) : (
            <div className="whitespace-pre-wrap text-[15px] leading-6">{message.content}</div>
          )}

          </div>

          {/* Timestamp and Feedback bar */}
          <div className={`flex w-full items-center gap-2 px-1 ${isAssistant ? "justify-between" : "justify-end"}`}>
            <span className="text-[11px] text-dental-textSecondary">
            {message.created_at ? new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          </div>

          {isAssistant && message.id && (
            <div className="relative flex flex-wrap items-center gap-1 px-1">
              <button type="button" onClick={handleCopy} className="rounded-lg p-1.5 text-dental-textSecondary hover:bg-dental-card hover:text-dental-textPrimary" title="Copy">
                <Copy size={17} />
              </button>
              <button
                type="button"
                onClick={() => handleFeedback(5, "helpful")}
                disabled={feedbackGiven !== null}
                className={`rounded-lg p-1.5 transition-all hover:bg-dental-card ${feedbackGiven === "helpful" ? "text-dental-accent" : "text-dental-textSecondary hover:text-dental-textPrimary"}`}
                title="Like"
              >
                <ThumbsUp size={17} />
              </button>
              <button
                type="button"
                onClick={() => handleFeedback(1, "needs-work")}
                disabled={feedbackGiven !== null}
                className={`rounded-lg p-1.5 transition-all hover:bg-dental-card ${feedbackGiven === "needs-work" ? "text-red-400" : "text-dental-textSecondary hover:text-dental-textPrimary"}`}
                title="Dislike"
              >
                <ThumbsDown size={17} />
              </button>
              <button type="button" onClick={handleShare} className="rounded-lg p-1.5 text-dental-textSecondary hover:bg-dental-card hover:text-dental-textPrimary" title="Share">
                <Share2 size={17} />
              </button>
              <button type="button" onClick={handleRetry} className="rounded-lg p-1.5 text-dental-textSecondary hover:bg-dental-card hover:text-dental-textPrimary" title="Try again">
                <RotateCcw size={17} />
              </button>
              <button type="button" onClick={() => setShowMore((current) => !current)} className="rounded-lg p-1.5 text-dental-textSecondary hover:bg-dental-card hover:text-dental-textPrimary" title="More actions">
                <MoreHorizontal size={17} />
              </button>
              {message.sources?.length > 0 && (
                <button
                  type="button"
                  onClick={() => setShowSources((current) => !current)}
                  className="ml-1 inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium text-dental-textSecondary hover:bg-dental-card hover:text-dental-textPrimary"
                >
                  <BookOpen size={17} />
                  Sources
                </button>
              )}

              {showMore && (
                <div className="absolute left-28 top-9 z-20 w-56 rounded-2xl border border-dental-border bg-dental-card p-2 shadow-2xl">
                  <p className="px-3 py-2 text-xs text-dental-textSecondary">
                    {message.created_at ? new Date(message.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "Assistant response"}
                  </p>
                  <button type="button" onClick={() => setShowMore(false)} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-dental-textPrimary hover:bg-dental-border">
                    <Volume2 className="h-4 w-4 text-dental-textSecondary" />
                    Read aloud
                  </button>
                  <button type="button" onClick={() => setShowMore(false)} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-dental-textPrimary hover:bg-dental-border">
                    <RotateCcw className="h-4 w-4 text-dental-textSecondary" />
                    Try again
                  </button>
                </div>
              )}
            </div>
          )}

          {isAssistant && showSources && message.sources && message.sources.length > 0 && (
            <div className="mx-1 mt-2 rounded-2xl border border-dental-border bg-dental-card p-3">
              <p className="mb-2 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-dental-accent">
                <FileText size={12} /> Grounded Sources
              </p>
              <div className="flex flex-wrap gap-1.5">
                {message.sources.map((source, index) => (
                  source.source_type === "web" && source.url ? (
                    <a
                      key={index}
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 rounded-full border border-dental-border bg-dental-darkBg px-2.5 py-1 text-[11px] text-dental-textSecondary transition-colors hover:text-dental-textPrimary"
                      title={source.url}
                    >
                      <Globe2 size={10} className="shrink-0 text-sky-400" />
                      <span className="max-w-[150px] truncate">{source.document_name}</span>
                    </a>
                  ) : (
                    <span
                      key={index}
                      className="inline-flex items-center gap-1 rounded-full border border-dental-border bg-dental-darkBg px-2.5 py-1 text-[11px] text-dental-textSecondary transition-colors hover:text-dental-textPrimary"
                      title={`Source chunk: ${source.chunk_index}, confidence score: ${source.score ? (source.score * 100).toFixed(0) : "N/A"}%`}
                    >
                      <FileText size={10} className="shrink-0 text-teal-500" />
                      <span className="max-w-[120px] truncate">{source.document_name}</span>
                      {source.page_number && <span className="opacity-60">p.{source.page_number}</span>}
                    </span>
                  )
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </article>
  );
}
