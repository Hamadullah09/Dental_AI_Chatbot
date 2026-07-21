"use client";

import React from "react";
import { Download } from "lucide-react";
import type { Message } from "@/lib/types";
import { MessageBubble } from "./MessageBubble";
import { useChatbotConfig } from "@/lib/chatbot-config";

interface ChatWindowProps {
  messages: Message[];
  isLoading: boolean;
  thinkingMessage?: string;
  onQuickAction: (actionText: string) => void;
  onStatus: (status: string) => void;
  onRetryMessage: (question: string) => void;
  onFollowUpClick?: (question: string) => void;
  onExportChat?: () => void;
  chatWindowRef: React.RefObject<HTMLDivElement>;
  bottomRef: React.RefObject<HTMLDivElement>;
}

export function ChatWindow({
  messages,
  isLoading,
  thinkingMessage,
  onStatus,
  onQuickAction,
  onRetryMessage,
  onFollowUpClick,
  onExportChat,
  chatWindowRef,
  bottomRef,
}: ChatWindowProps) {
  const config = useChatbotConfig();
  const isChatEmpty = messages.length === 0;

  function previousUserQuestion(index: number) {
    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      if (messages[cursor]?.role === "user" && messages[cursor]?.content) {
        return messages[cursor].content.replace(/^Attached PDF:[^\n]*\n\n/, "").trim();
      }
    }
    return "";
  }

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
              <h1 className="text-3xl font-semibold tracking-tight text-dental-textPrimary sm:text-4xl">{config.welcome_message}</h1>
              <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-dental-textSecondary sm:text-base">
                {config.chatbot_tagline}
              </p>
              <div className="mt-6 grid gap-2 sm:grid-cols-2">
                {config.suggested_questions.map((prompt) => (
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
            <div className="flex items-center justify-between px-1 mb-2">
              <span className="text-[11px] text-dental-textSecondary">{messages.length > 1 ? `${Math.ceil(messages.length / 2)} exchange(s)` : ""}</span>
              {messages.length > 0 && onExportChat && (
                <button
                  type="button"
                  onClick={onExportChat}
                  className="inline-flex items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-[11px] font-medium text-dental-textSecondary hover:bg-dental-card hover:text-dental-textPrimary transition-colors"
                >
                  <Download size={13} />
                  Export Chat
                </button>
              )}
            </div>
            {messages.map((message, index) => (
              (message.role === "assistant" && !message.content.trim() && (!message.sources || message.sources.length === 0) && (!message.visuals || message.visuals.length === 0)) ? null : (
              <MessageBubble 
                key={message.id} 
                message={message} 
                onStatus={onStatus} 
                onRetry={message.role === "assistant" ? () => {
                  const question = previousUserQuestion(index);
                  if (question) onRetryMessage(question);
                } : undefined}
                onFollowUpClick={onFollowUpClick}
              />
              )
            ))}

            {/* Typing Indicator */}
            {isLoading && (
              <div id="typingIndicator" className="flex w-full justify-start px-1 py-5 fade-in">
                <div className="flex items-center gap-3 rounded-2xl border border-dental-border bg-dental-card px-4 py-3 shadow-sm">
                  <div className="flex gap-1">
                    <div className="typing-dot h-2 w-2 rounded-full bg-dental-accent"></div>
                    <div className="typing-dot h-2 w-2 rounded-full bg-dental-accent"></div>
                    <div className="typing-dot h-2 w-2 rounded-full bg-dental-accent"></div>
                  </div>
                  <span className="text-xs text-dental-textSecondary">{thinkingMessage || config.typing_message}</span>
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
