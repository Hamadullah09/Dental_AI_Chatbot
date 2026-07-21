"use client";

import React, { useState } from "react";
import Image from "next/image";
import { useAuth } from "@/lib/auth";
import { BookOpen, Copy, FileImage, FileText, Globe2, MoreHorizontal, RotateCcw, Share2, ThumbsDown, ThumbsUp, Volume2 } from "lucide-react";
import type { Message } from "@/lib/types";
import { sendFeedback } from "@/lib/api";
import { SafeMarkdown } from "./SafeMarkdown";

interface MessageBubbleProps {
  message: Message;
  onStatus?: (status: string) => void;
  onRetry?: () => void;
}

export function MessageBubble({ message, onStatus, onRetry }: MessageBubbleProps) {
  const { token } = useAuth();
  const [feedbackGiven, setFeedbackGiven] = useState<"helpful" | "needs-work" | null>(null);
  const [showSources, setShowSources] = useState(false);
  const [showMore, setShowMore] = useState(false);
  const isAssistant = message.role === "assistant";
  const hasRenderableContent = (message.content || "").trim().length > 0;

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
    await navigator.clipboard?.writeText(message.content || "");
    onStatus?.("Copied response.");
    setTimeout(() => onStatus?.(""), 2000);
  }

  async function handleShare() {
    if (navigator.share) {
      await navigator.share({ title: "Dental AI response", text: message.content || "" });
      return;
    }
    await handleCopy();
  }

  function handleRetry() {
    if (!onRetry) {
      onStatus?.("No previous question is available to retry.");
      setTimeout(() => onStatus?.(""), 3000);
      return;
    }
    onRetry();
  }

  function handleReadAloud() {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      onStatus?.("Read aloud is not supported in this browser.");
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(message.content);
    utterance.rate = 0.95;
    window.speechSynthesis.speak(utterance);
    onStatus?.("Reading response aloud.");
    setShowMore(false);
  }

  return (
    <article className={`fade-in w-full py-4 ${message.role === "user" ? "flex justify-end" : "flex justify-start"}`}>
      <div className={`${isAssistant ? "w-full max-w-3xl" : "max-w-[88%] sm:max-w-[72%]"}`}>
        {/* Bubble Content */}
        <div className={`flex min-w-0 flex-1 flex-col gap-2 ${isAssistant ? "" : "items-end"}`}>
          <div className={`max-w-full text-sm leading-relaxed ${
            message.role === "user"
              ? "rounded-[1.65rem] bg-dental-userBubble px-5 py-3 text-dental-userBubbleText shadow-sm"
              : "w-full px-1 py-1 text-dental-textPrimary"
          }`}>
          {/* Main Text */}
          {isAssistant ? (
            <div className="break-words">
              <SafeMarkdown content={message.content} />
            </div>
          ) : (
            <div className="whitespace-pre-wrap text-[15px] leading-6">{message.content}</div>
          )}

          </div>

          {isAssistant && message.visuals && message.visuals.length > 0 && (
            <div className="mx-1 mt-2 rounded-2xl border border-dental-border bg-dental-card p-3">
              <p className="mb-3 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-dental-accent">
                <FileImage size={12} /> Related Visuals
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                {message.visuals.map((visual) => (
                  <a
                    key={visual.visual_id}
                    href={visual.image_url}
                    target="_blank"
                    rel="noreferrer"
                    className="group overflow-hidden rounded-xl border border-dental-border bg-dental-elevated transition-colors hover:border-dental-accent/50"
                  >
                    <div className="aspect-[4/3] w-full overflow-hidden bg-dental-muted">
                      <Image
                        src={visual.image_url}
                        alt={visual.caption_text || `${visual.visual_type} from ${visual.document_name}`}
                        width={480}
                        height={360}
                        unoptimized
                        className="h-full w-full object-cover transition-transform group-hover:scale-[1.02]"
                        loading="lazy"
                      />
                    </div>
                    <div className="space-y-1 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="rounded-full bg-dental-accentSoft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-dental-accent">
                          {(visual.visual_type || "image").replace("_", " ")}
                        </span>
                        {visual.page_number && <span className="text-[10px] text-dental-textMuted">p.{visual.page_number}</span>}
                      </div>
                      <p className="truncate text-xs font-semibold text-dental-textPrimary">{visual.document_name}</p>
                      {(visual.caption_text || visual.generated_description) && (
                        <p className="line-clamp-2 text-[11px] leading-5 text-dental-textSecondary">
                          {visual.caption_text || visual.generated_description}
                        </p>
                      )}
                    </div>
                  </a>
                ))}
              </div>
            </div>
          )}

          {/* Timestamp and Feedback bar */}
          {(!isAssistant || hasRenderableContent) && (
          <div className={`flex w-full items-center gap-2 px-1 ${isAssistant ? "justify-between" : "justify-end"}`}>
            <span className="text-[11px] text-dental-textSecondary">
            {message.created_at ? new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          </div>
          )}

          {isAssistant && message.id && hasRenderableContent && (
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
                  <button type="button" onClick={handleReadAloud} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-dental-textPrimary hover:bg-dental-border">
                    <Volume2 className="h-4 w-4 text-dental-textSecondary" />
                    Read aloud
                  </button>
                  <button type="button" onClick={handleRetry} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-dental-textPrimary hover:bg-dental-border">
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
