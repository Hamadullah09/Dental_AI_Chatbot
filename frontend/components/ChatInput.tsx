"use client";

import React, { useRef, ChangeEvent, KeyboardEvent } from "react";
import { Paperclip, Mic, ArrowUp, X, FileText, ImageIcon, Square } from "lucide-react";

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
    <div className="w-full border-t border-dental-border bg-dental-darkBg p-4">
      <form onSubmit={onSubmit} className="max-w-3xl mx-auto relative flex flex-col gap-2">
        {/* Attachment Preview Card */}
        {attachment && (
          <div className="flex items-center gap-2.5 p-2 bg-dental-card border border-dental-border rounded-xl w-fit max-w-xs animate-in fade-in slide-in-from-bottom-2 duration-150">
            {attachment.type.startsWith("image/") ? (
              <ImageIcon className="text-purple-400 shrink-0" size={16} />
            ) : (
              <FileText className="text-teal-400 shrink-0" size={16} />
            )}
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

        <div className="flex items-end gap-2">
          {/* File Input (Hidden) */}
          <input
            type="file"
            ref={fileInputRef}
            onChange={onFileChange}
            className="hidden"
            accept="application/pdf"
          />

          {/* Plus/Clip attachment icon */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="p-3 text-dental-textSecondary hover:text-dental-textPrimary hover:bg-dental-card rounded-full transition-colors flex-shrink-0"
            title="Attach Report, Prescription, or X-ray"
          >
            <Paperclip className="w-5 h-5" />
          </button>

          {/* Text Area */}
          <div className="flex-1 bg-dental-card border border-dental-border rounded-2xl flex items-center px-4 py-2.5 focus-within:border-dental-accent focus-within:ring-1 focus-within:ring-dental-accent/40 transition-all shadow-sm">
            <textarea
              ref={textareaRef}
              rows={1}
              value={value}
              onChange={(e) => {
                onChange(e.target.value);
                adjustHeight();
              }}
              onKeyDown={handleKeyDown}
              placeholder="Ask about tooth pain, braces, whitening, reports, or appointments"
              className="w-full bg-transparent border-none focus:ring-0 text-dental-textPrimary placeholder:text-dental-textSecondary resize-none max-h-40 py-1.5 focus:outline-none scrollbar-hide text-sm"
            />
          </div>

          {/* Voice Input */}
          <div className="relative hidden sm:flex items-center justify-center flex-shrink-0">
            {isListening && (
              <>
                <span className="absolute h-12 w-12 rounded-full bg-red-400/20 animate-ping" />
                <span className="absolute h-10 w-10 rounded-full border border-red-300/50" />
              </>
            )}
            <button
              type="button"
              onClick={onToggleVoice}
              aria-pressed={isListening}
              className={`relative z-10 h-11 min-w-11 px-3 rounded-full transition-all flex items-center justify-center gap-2 border shadow-sm ${
                isListening
                  ? "bg-red-500 text-white border-red-400 shadow-red-500/20"
                  : "bg-dental-card text-dental-textSecondary hover:text-dental-textPrimary hover:border-dental-accent border-dental-border"
              }`}
              title={isListening ? "Stop listening" : "Voice to text"}
            >
              {isListening ? (
                <>
                  <Square className="w-4 h-4 fill-current" />
                  <span className="text-[11px] font-bold pr-1">Stop</span>
                </>
              ) : (
                <Mic className="w-5 h-5" />
              )}
            </button>
          </div>

          {/* Send Button */}
          <button
            type="submit"
            disabled={isLoading || (!value.trim() && !attachment)}
            className="p-3 bg-dental-accent hover:bg-dental-accentHover disabled:opacity-45 disabled:pointer-events-none text-white rounded-full transition-colors flex-shrink-0 shadow-lg shadow-dental-accent/15"
            title="Send message"
          >
            <ArrowUp className="w-5 h-5 text-white" />
          </button>
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
