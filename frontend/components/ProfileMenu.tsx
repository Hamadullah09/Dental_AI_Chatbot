"use client";

import { useAuth } from "@/lib/auth";
import { LogOut, Sparkles, Settings, HelpCircle, ArrowUpCircle } from "lucide-react";

interface ProfileMenuProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenModal: (modalName: string) => void;
}

export function ProfileMenu({ isOpen, onClose, onOpenModal }: ProfileMenuProps) {
  const { user, logout } = useAuth();

  if (!isOpen) return null;

  return (
    <div className="absolute bottom-full left-3 right-3 mb-2 bg-dental-card border border-dental-border rounded-xl shadow-2xl py-1 z-50">
      <div className="px-3 py-2 border-b border-dental-border">
        <p className="text-xs text-dental-textSecondary truncate">Signed in as</p>
        <p className="text-sm font-semibold text-white truncate">{user?.email || "patient@example.com"}</p>
      </div>
      <button
        onClick={() => {
          onOpenModal("upgrade");
          onClose();
        }}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-300 hover:bg-white/5 hover:text-white transition-colors text-left"
      >
        <ArrowUpCircle size={16} className="text-dental-accent" />
        <span>Upgrade Plan</span>
      </button>
      <button
        onClick={() => {
          onOpenModal("personalization");
          onClose();
        }}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-300 hover:bg-white/5 hover:text-white transition-colors text-left"
      >
        <Sparkles size={16} className="text-yellow-400" />
        <span>Personalization</span>
      </button>
      <button
        onClick={() => {
          onOpenModal("settings");
          onClose();
        }}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-300 hover:bg-white/5 hover:text-white transition-colors text-left"
      >
        <Settings size={16} />
        <span>Settings</span>
      </button>
      <button
        onClick={() => {
          onOpenModal("tips");
          onClose();
        }}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-300 hover:bg-white/5 hover:text-white transition-colors text-left"
      >
        <HelpCircle size={16} />
        <span>Help & Support</span>
      </button>
      <div className="border-t border-dental-border my-1"></div>
      <button
        onClick={() => {
          logout();
        }}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-white/5 transition-colors text-left"
      >
        <LogOut size={16} />
        <span>Log out</span>
      </button>
    </div>
  );
}
