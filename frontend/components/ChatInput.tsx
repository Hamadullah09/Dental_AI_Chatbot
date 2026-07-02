"use client";

import React, { useRef, ChangeEvent, KeyboardEvent } from "react";
import { Globe2, Paperclip, Mic, ArrowUp, X, FileText, Square } from "lucide-react";

interface ChatInputProps {
  value: string;
  onChange: (val: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  isLoading: boolean;
  fileInputRef: React.RefObject<HTMLInputElement>;
  onFileChange: (e: ChangeEvent<HTMLInputElement>) => void;
  attachment: File | null;
  onRemoveAttachment: () => void;
  isListening: boolean;
  onToggleVoice: () => void;
  searchWeb: boolean;
  onToggleSearchWeb: () => void;
}

export function ChatInput({
  value,
  onChange,
  onSubmit,
  isLoading,
  fileInputRef,
  onFileChange,
  attachment,
  onRemoveAttachment,
  isListening,
  onToggleVoice,
  searchWeb,
  onToggleSearchWeb,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isLoading && (value.trim() || attachment)) {
        onSubmit(e);
      }
    }
  };

  const adjustHeight = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  };

  return (
    <div className="w-full border-t border-dental-border bg-dental-darkBg/95 px-3 py-3 backdrop-blur md:px-4">
      <form onSubmit={onSubmit} className="relative mx-auto flex w-full max-w-3xl flex-col gap-2">
        {/* Attachment Preview Card */}
        {attachment && (
          <div className="flex w-fit max-w-full items-center gap-2.5 rounded-2xl border border-dental-border bg-dental-card p-2 pr-2.5 animate-in fade-in slide-in-from-bottom-2 duration-150">
            <FileText className="shrink-0 text-dental-accent" size={16} />
            <div className="flex-1 min-w-0">
              <p className="text-xs text-dental-textPrimary truncate font-medium">{attachment.name}</p>
              <p className="text-[10px] text-dental-textSecondary">
                {(attachment.size / 1024).toFixed(1)} KB
              </p>
            </div>
            <button
              type="button"
              onClick={onRemoveAttachment}
              className="text-dental-textSecondary hover:text-dental-textPrimary p-1 hover:bg-dental-border rounded-lg transition-colors shrink-0"
              title="Remove attachment"
            >
              <X size={14} />
            </button>
          </div>
        )}

        <div className="rounded-3xl border border-dental-border bg-dental-card shadow-lg shadow-black/10 transition-all focus-within:border-dental-accent/70 focus-within:ring-1 focus-within:ring-dental-accent/30">
          {/* File Input (Hidden) */}
          <input
            type="file"
            ref={fileInputRef}
            onChange={onFileChange}
            className="hidden"
            accept="application/pdf"
          />

          {/* Text Area */}
          <div className="flex items-end px-4 pt-3">
            <textarea
              ref={textareaRef}
              rows={1}
              value={value}
              onChange={(e) => {
                onChange(e.target.value);
                adjustHeight();
              }}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything about dental care..."
              className="max-h-40 min-h-[36px] w-full resize-none bg-transparent py-1.5 text-[15px] leading-6 text-dental-textPrimary placeholder:text-dental-textSecondary focus:outline-none scrollbar-hide"
            />
          </div>

          <div className="flex items-center justify-between gap-2 px-3 pb-3 pt-1">
            <div className="flex items-center gap-1.5">
              {/* Plus/Clip attachment icon */}
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="flex h-9 w-9 items-center justify-center rounded-full text-dental-textSecondary transition-colors hover:bg-dental-border hover:text-dental-textPrimary"
                title="Attach PDF"
              >
                <Paperclip className="h-5 w-5" />
              </button>

              <button
                type="button"
                onClick={onToggleSearchWeb}
                className={`flex h-9 items-center gap-1.5 rounded-full px-3 text-xs font-medium transition-colors ${
                  searchWeb
                    ? "bg-dental-accent/15 text-dental-accent"
                    : "text-dental-textSecondary hover:bg-dental-border hover:text-dental-textPrimary"
                }`}
                title={searchWeb ? "Web search on" : "Search trusted web sources"}
              >
                <Globe2 className="h-4 w-4" />
                <span className="hidden sm:inline">Web</span>
              </button>
            </div>

            <div className="flex items-center gap-1.5">
              {/* Voice Input */}
              <div className="relative flex items-center justify-center">
                {isListening && <span className="absolute h-10 w-10 rounded-full bg-red-400/20 animate-ping" />}
                <button
                  type="button"
                  onClick={onToggleVoice}
                  aria-pressed={isListening}
                  className={`relative z-10 flex h-9 min-w-9 items-center justify-center gap-1.5 rounded-full px-2.5 transition-colors ${
                    isListening
                      ? "bg-red-500 text-white"
                      : "text-dental-textSecondary hover:bg-dental-border hover:text-dental-textPrimary"
                  }`}
                  title={isListening ? "Stop listening" : "Voice to text"}
                >
                  {isListening ? (
                    <>
                      <Square className="h-3.5 w-3.5 fill-current" />
                      <span className="hidden text-[11px] font-semibold sm:inline">Stop</span>
                    </>
                  ) : (
                    <Mic className="h-5 w-5" />
                  )}
                </button>
              </div>

              {/* Send Button */}
              <button
                type="submit"
                disabled={isLoading || (!value.trim() && !attachment)}
                className="flex h-9 w-9 items-center justify-center rounded-full bg-dental-textPrimary text-dental-darkBg transition-colors hover:opacity-90 disabled:pointer-events-none disabled:opacity-40"
                title="Send message"
              >
                <ArrowUp className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </form>
      <div className="text-center mt-2">
        <p className="text-[10px] text-dental-textSecondary">
          Dental AI can make mistakes. Consult a professional dentist for medical advice.
        </p>
      </div>
    </div>
  );
}
