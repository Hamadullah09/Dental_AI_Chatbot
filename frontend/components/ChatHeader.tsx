"use client";

import { Menu, Sun, Moon, Stethoscope } from "lucide-react";
import { useTheme } from "@/lib/theme";

interface ChatHeaderProps {
  onMenuToggle: () => void;
}

export function ChatHeader({ onMenuToggle }: ChatHeaderProps) {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="flex items-center justify-between p-4 border-b border-dental-border bg-dental-darkBg/80 backdrop-blur-md sticky top-0 z-30 w-full min-h-[64px]">
      {/* Mobile Menu Toggle */}
      <div className="flex items-center gap-2">
        <button 
          onClick={onMenuToggle}
          className="lg:hidden p-2 -ml-2 text-dental-textSecondary hover:text-dental-textPrimary rounded-lg hover:bg-dental-card transition-colors"
          aria-label="Toggle sidebar"
        >
          <Menu className="w-6 h-6" />
        </button>
        <div className="flex items-center gap-2 lg:hidden">
          <div className="bg-dental-accent/10 p-1.5 rounded-lg">
            <Stethoscope className="text-dental-accent w-4 h-4" />
          </div>
          <span className="font-semibold text-dental-textPrimary text-sm">Dental AI</span>
        </div>
      </div>

      {/* Center Spacer instead of model badge */}
      <div className="flex-1" />

      {/* Right side Theme Toggle */}
      <button 
        type="button"
        onClick={toggleTheme}
        className="p-2 text-dental-textSecondary hover:text-dental-textPrimary hover:bg-dental-card rounded-xl transition-colors"
        aria-label="Toggle theme"
      >
        {theme === "dark" ? <Sun className="w-5 h-5 text-yellow-400" /> : <Moon className="w-5 h-5" />}
      </button>
    </header>
  );
}

