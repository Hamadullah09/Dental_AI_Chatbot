"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { 
  FolderOpen, Calendar, FileText, Sparkles, Settings, 
  MessageSquare, Plus, Search, ChevronUp, Tooth, X 
} from "lucide-react";
import type { ChatSession } from "@/lib/types";
import { ProfileMenu } from "./ProfileMenu";

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onOpenModal: (modalName: string) => void;
}

export function Sidebar({
  isOpen,
  onClose,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onOpenModal,
}: SidebarProps) {
  const { user } = useAuth();
  const [searchQuery, setSearchQuery] = useState("");
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);

  const initials = user?.full_name
    ? user.full_name.split(" ").map((n) => n[0]).join("").toUpperCase().substring(0, 2)
    : user?.email ? user.email.substring(0, 2).toUpperCase() : "JD";

  const filteredSessions = sessions.filter((session) => 
    (session.title || "Untitled Consultation").toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <>
      {/* Mobile Sidebar Overlay */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/60 z-40 lg:hidden backdrop-blur-sm"
          onClick={onClose}
        />
      )}

      {/* Sidebar Container */}
      <aside 
        className={`fixed inset-y-0 left-0 z-50 w-72 bg-dental-sidebar border-r border-dental-border flex flex-col transform transition-transform duration-300 lg:relative lg:translate-x-0 h-full ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Brand Header */}
        <div className="p-4 flex items-center justify-between border-b border-dental-border">
          <div className="flex items-center gap-2">
            <div className="bg-dental-accent/10 p-2 rounded-lg">
              <Tooth className="text-dental-accent w-6 h-6" />
            </div>
            <span className="font-semibold text-lg tracking-tight text-white">Dental AI Assistant</span>
          </div>
          <button onClick={onClose} className="lg:hidden text-gray-400 hover:text-white p-1 rounded">
            <X size={20} />
          </button>
        </div>

        {/* New Consultation Button */}
        <div className="px-3 pt-4 pb-2">
          <button 
            onClick={() => {
              onNewChat();
              onClose();
            }}
            className="w-full flex items-center justify-center gap-3 px-3 py-3 bg-dental-card hover:bg-dental-border border border-dental-border rounded-xl transition-all text-sm group text-white font-medium"
          >
            <Plus className="w-4 h-4 text-dental-textSecondary group-hover:text-dental-accent transition-colors" />
            <span>New Consultation</span>
          </button>
        </div>

        {/* Search History */}
        <div className="px-3 py-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input 
              type="text" 
              placeholder="Search history..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-dental-darkBg border border-dental-border rounded-lg py-2 pl-9 pr-3 text-sm text-white focus:outline-none focus:border-dental-accent transition-colors placeholder-gray-600"
            />
          </div>
        </div>

        {/* Navigation Section */}
        <nav className="flex-1 px-3 overflow-y-auto space-y-1 py-2">
          <button 
            onClick={() => { onOpenModal("library"); onClose(); }}
            className="w-full flex items-center gap-3 px-3 py-2 text-sm text-dental-textSecondary hover:text-white hover:bg-dental-card rounded-lg transition-colors text-left"
          >
            <FolderOpen className="w-4 h-4 text-teal-400" /> 
            <span>Patient Library</span>
          </button>
          <button 
            onClick={() => { onOpenModal("appointments"); onClose(); }}
            className="w-full flex items-center gap-3 px-3 py-2 text-sm text-dental-textSecondary hover:text-white hover:bg-dental-card rounded-lg transition-colors text-left"
          >
            <Calendar className="w-4 h-4 text-sky-400" /> 
            <span>Appointments</span>
          </button>
          <button 
            onClick={() => { onOpenModal("reports"); onClose(); }}
            className="w-full flex items-center gap-3 px-3 py-2 text-sm text-dental-textSecondary hover:text-white hover:bg-dental-card rounded-lg transition-colors text-left"
          >
            <FileText className="w-4 h-4 text-purple-400" /> 
            <span>Reports</span>
          </button>
          <button 
            onClick={() => { onOpenModal("tips"); onClose(); }}
            className="w-full flex items-center gap-3 px-3 py-2 text-sm text-dental-textSecondary hover:text-white hover:bg-dental-card rounded-lg transition-colors text-left"
          >
            <Sparkles className="w-4 h-4 text-yellow-400" /> 
            <span>Dental Tips</span>
          </button>
          <button 
            onClick={() => { onOpenModal("settings"); onClose(); }}
            className="w-full flex items-center gap-3 px-3 py-2 text-sm text-dental-textSecondary hover:text-white hover:bg-dental-card rounded-lg transition-colors text-left"
          >
            <Settings className="w-4 h-4 text-gray-400" /> 
            <span>Settings</span>
          </button>

          {/* Admin Workspace route if user is admin */}
          {user?.role === "admin" && (
            <button 
              onClick={() => { onOpenModal("admin"); onClose(); }}
              className="w-full flex items-center gap-3 px-3 py-2 text-sm text-red-400 hover:text-white hover:bg-dental-card rounded-lg transition-colors text-left"
            >
              <Settings className="w-4 h-4 text-red-400" /> 
              <span>Admin Workspace</span>
            </button>
          )}

          {/* Recent Chats */}
          <div className="pt-4 mt-4 border-t border-dental-border">
            <p className="px-3 text-xs font-semibold text-gray-600 mb-2 uppercase tracking-wider">Recent Chats</p>
            <div className="space-y-1">
              {filteredSessions.length ? (
                filteredSessions.map((session) => (
                  <button 
                    key={session.id}
                    onClick={() => {
                      onSelectSession(session.id);
                      onClose();
                    }}
                    className={`w-full flex items-center gap-3 px-3 py-2 text-sm rounded-lg transition-colors text-left truncate ${
                      activeSessionId === session.id 
                        ? "bg-dental-border text-white border-l-2 border-dental-accent" 
                        : "text-gray-400 hover:text-white hover:bg-dental-card"
                    }`}
                  >
                    <MessageSquare className="w-4 h-4 shrink-0 text-dental-accent/60" />
                    <span className="truncate">{session.title || "Untitled chat"}</span>
                  </button>
                ))
              ) : (
                <p className="px-3 text-xs text-gray-600 italic">No matching chats</p>
              )}
            </div>
          </div>
        </nav>

        {/* User Profile Footer */}
        <div className="p-3 border-t border-dental-border relative bg-dental-sidebar">
          <button 
            onClick={() => setIsProfileMenuOpen(!isProfileMenuOpen)} 
            className="w-full flex items-center gap-3 p-2 rounded-xl hover:bg-dental-card transition-colors text-left"
          >
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-dental-accent to-blue-600 flex items-center justify-center text-white font-bold text-sm shrink-0">
              {initials}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-white truncate">{user?.full_name || user?.email || "Wazeer Ali"}</p>
              <p className="text-xs text-dental-accent truncate font-medium">
                {user?.role === "admin" ? "Admin Account" : "Premium Plan"}
              </p>
            </div>
            <ChevronUp className="w-4 h-4 text-gray-500" />
          </button>

          {/* Profile Dropdown Menu */}
          <ProfileMenu 
            isOpen={isProfileMenuOpen}
            onClose={() => setIsProfileMenuOpen(false)}
            onOpenModal={onOpenModal}
          />
        </div>
      </aside>
    </>
  );
}
