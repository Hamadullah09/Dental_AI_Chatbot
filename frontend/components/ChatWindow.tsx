"use client";

import React from "react";
import type { Message } from "@/lib/types";
import { MessageBubble } from "./MessageBubble";

interface ChatWindowProps {
  messages: Message[];
  isLoading: boolean;
  onQuickAction: (actionText: string) => void;
  onStatus: (status: string) => void;
  onRetryMessage: (question: string) => void;
  chatWindowRef: React.RefObject<HTMLDivElement>;
  bottomRef: React.RefObject<HTMLDivElement>;
}

export function ChatWindow({
  messages,
  isLoading,
  onStatus,
  onQuickAction,
  onRetryMessage,
  chatWindowRef,
  bottomRef,
}: ChatWindowProps) {
  const isChatEmpty = messages.length === 0;

  function previousUserQuestion(index: number) {
    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      if (messages[cursor]?.role === "user") {
        return messages[cursor].content.replace(/^Attached PDF:[^\n]*\n\n/, "").trim();
      }
    }
    return "";
  }

  const suggestedPrompts = [
    "What is dental caries?",
    "Explain gingivitis in simple words.",
    "Summarize an uploaded dental PDF.",
    "Explain this answer in Roman Urdu.",
  ];

  return (
    <div 
      ref={chatWindowRef}
      className="flex-1 overflow-y-auto scroll-smooth"
    >
      <div className="mx-auto flex min-h-full w-full max-w-4xl flex-col px-4 py-6 sm:px-6 md:px-8">
        
        {isChatEmpty ? (
          /* Welcome Screen (Empty State) */
          <div className="flex flex-1 items-center justify-center py-8 fade-in">
            <div className="mx-auto w-full max-w-2xl text-center">
              <h1 className="text-3xl font-semibold tracking-tight text-dental-textPrimary sm:text-4xl">How can I help?</h1>
              <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-dental-textSecondary sm:text-base">
                Ask questions about dental care, symptoms, treatments, and general oral health guidance.
              </p>
              <div className="mt-6 grid gap-2 sm:grid-cols-2">
                {suggestedPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => onQuickAction(prompt)}
                    className="rounded-2xl border border-dental-border bg-dental-card px-4 py-3 text-left text-sm font-medium text-dental-textPrimary transition-colors hover:border-dental-accent/50 hover:bg-dental-elevated"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          /* Active Chat Conversation View */
          <div className="flex w-full flex-col gap-1 pb-28">
            {messages.map((message, index) => (
              <MessageBubble 
                key={message.id} 
                message={message} 
                onStatus={onStatus} 
                onRetry={message.role === "assistant" ? () => {
                  const question = previousUserQuestion(index);
                  if (question) onRetryMessage(question);
                } : undefined}
              />
            ))}

            {/* Typing Indicator */}
            {isLoading && (
              <div id="typingIndicator" className="flex w-full justify-start px-1 py-5 fade-in">
                <div className="flex h-10 items-center gap-1 rounded-2xl border border-dental-border bg-dental-card px-4 shadow-sm">
                  <div className="typing-dot h-2 w-2 rounded-full bg-dental-textSecondary"></div>
                  <div className="typing-dot h-2 w-2 rounded-full bg-dental-textSecondary"></div>
                  <div className="typing-dot h-2 w-2 rounded-full bg-dental-textSecondary"></div>
                </div>
              </div>
            )}
            
            <div ref={bottomRef} />
          </div>
        )}

      </div>
    </div>
  );
}
