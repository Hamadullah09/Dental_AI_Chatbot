"use client";

import { useState } from "react";
import { Archive, Menu, Moon, MoreHorizontal, Share2, Sun, Trash2 } from "lucide-react";
import { useTheme } from "@/lib/theme";

interface ChatHeaderProps {
  activeSessionId: string | null;
  onMenuToggle: () => void;
  onArchiveSession: (id: string) => Promise<void>;
  onDeleteSession: (id: string) => Promise<void>;
}

export function ChatHeader({ activeSessionId, onMenuToggle, onArchiveSession, onDeleteSession }: ChatHeaderProps) {
  const { theme, toggleTheme } = useTheme();
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  async function handleShare() {
    if (typeof window === "undefined") return;
    const url = window.location.href;
    if (navigator.share) {
      await navigator.share({ title: "Dental AI Chatbot", url });
      return;
    }
    await navigator.clipboard?.writeText(url);
  }

  async function handleArchive() {
    if (!activeSessionId) return;
    if (!window.confirm("Archive this chat?")) return;
    await onArchiveSession(activeSessionId);
    setIsMenuOpen(false);
  }

  async function handleDelete() {
    if (!activeSessionId) return;
    if (!window.confirm("Delete this chat permanently?")) return;
    await onDeleteSession(activeSessionId);
    setIsMenuOpen(false);
  }

  return (
    <header className="sticky top-0 z-30 flex w-full items-center justify-between border-b border-dental-border bg-dental-darkBg/90 px-3 sm:px-4 min-h-[64px] backdrop-blur-md">
      <div className="flex items-center gap-3">
        <button 
          onClick={onMenuToggle}
          className="inline-flex lg:hidden p-2 -ml-1 text-dental-textSecondary hover:text-dental-textPrimary rounded-xl hover:bg-dental-card transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60"
          aria-label="Toggle sidebar"
        >
          <Menu className="w-6 h-6" />
        </button>
      </div>

      <div className="flex-1" />

      <div className="relative flex items-center gap-1.5">
        <button
          type="button"
          onClick={handleShare}
          className="hidden sm:inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium text-dental-textPrimary hover:bg-dental-card transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60"
          aria-label="Share chat"
        >
          <Share2 className="h-4 w-4" />
          Share
        </button>
        <button
          type="button"
          onClick={toggleTheme}
          className="inline-flex p-2 text-dental-textSecondary hover:text-dental-textPrimary hover:bg-dental-card rounded-xl transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60"
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <Sun className="w-5 h-5 text-yellow-400" /> : <Moon className="w-5 h-5" />}
        </button>
        <button
          type="button"
          onClick={() => setIsMenuOpen((current) => !current)}
          className="inline-flex p-2 text-dental-textSecondary hover:text-dental-textPrimary hover:bg-dental-card rounded-xl transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60"
          aria-label="Open chat menu"
        >
          <MoreHorizontal className="h-5 w-5" />
        </button>

        {isMenuOpen && (
          <div className="absolute right-0 top-12 z-50 w-64 rounded-2xl border border-dental-border bg-dental-card p-2 shadow-2xl">
            {[
              { icon: Archive, label: "Archive", disabled: !activeSessionId, onClick: handleArchive },
            ].map((item) => (
              <button
                key={item.label}
                type="button"
                onClick={item.onClick}
                disabled={item.disabled}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-dental-textPrimary transition-colors hover:bg-dental-border disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60"
              >
                <item.icon className="h-4 w-4 text-dental-textSecondary" />
                {item.label}
              </button>
            ))}
            <button
              type="button"
              onClick={handleDelete}
              disabled={!activeSessionId}
              className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-red-400 transition-colors hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/40"
            >
              <Trash2 className="h-4 w-4" />
              Delete
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
