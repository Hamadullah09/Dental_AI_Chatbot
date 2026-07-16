"use client";

import { ReactNode, useState, useEffect, createContext, useContext, useCallback } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { archiveSession, deleteSession, getSessions } from "@/lib/api";
import type { ChatSession } from "@/lib/types";
import { Sidebar } from "./Sidebar";
import { ChatHeader } from "./ChatHeader";
import { FeatureModals } from "./FeatureModals";

// Define a context for child pages to trigger sidebar modals
interface ModalContextType {
  openModal: (modalName: string) => void;
  sessions: ChatSession[];
  refreshSessions: () => Promise<void>;
}

const ModalContext = createContext<ModalContextType | null>(null);

export function useModal() {
  const context = useContext(ModalContext);
  if (!context) {
    throw new Error("useModal must be used inside a ModalProvider (AppShell)");
  }
  return context;
}

export function AppShell({ title, subtitle, children }: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { token, user } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeModal, setActiveModal] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  // Fetch recent sessions from API
  const refreshSessions = useCallback(async () => {
    if (!token) return;
    try {
      const data = await getSessions(token);
      setSessions(data);
    } catch (error) {
      console.error("Failed to load sessions:", error);
    }
  }, [token]);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  useEffect(() => {
    setActiveSessionId(searchParams.get("session_id"));
  }, [pathname, searchParams]);

  const handleOpenModal = (modalName: string) => {
    if (modalName === "admin") {
      router.push("/admin");
    } else if (modalName === "profile") {
      router.push("/profile");
    } else if (modalName === "settings") {
      router.push("/settings");
    } else if (modalName === "appointments") {
      router.push("/appointments");
    } else if (modalName === "help") {
      router.push("/help");
    } else {
      setActiveModal(modalName);
    }
  };

  const handleSelectSession = (id: string) => {
    setActiveSessionId(id);
    router.push(`/chat?session_id=${id}`);
  };

  const handleNewChat = () => {
    setActiveSessionId(null);
    router.push("/chat");
  };

  const handleArchiveSession = async (id: string) => {
    if (!token) return;
    await archiveSession(id, token);
    if (activeSessionId === id) {
      handleNewChat();
    }
    await refreshSessions();
  };

  const handleDeleteSession = async (id: string) => {
    if (!token) return;
    await deleteSession(id, token);
    if (activeSessionId === id) {
      handleNewChat();
    }
    await refreshSessions();
  };

  const handleSendAttachedMessage = (filename: string, content: string) => {
    // Save info to local storage so chat page can capture it on reload
    localStorage.setItem("dental_ai_attached_file", filename);
    localStorage.setItem("dental_ai_attached_prompt", content);
    
    // Redirect to chat
    if (pathname === "/chat") {
      window.dispatchEvent(new Event("dental_ai_trigger_attachment_send"));
    } else {
      router.push("/chat");
    }
  };

  return (
    <ModalContext.Provider value={{ openModal: handleOpenModal, sessions, refreshSessions }}>
      <div className="h-dvh w-screen overflow-hidden flex bg-dental-darkBg text-dental-textPrimary selection:bg-dental-accent selection:text-white font-sans">
        
        {/* Sidebar Navigation */}
        <Sidebar 
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          isCollapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed((current) => !current)}
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelectSession={handleSelectSession}
          onNewChat={handleNewChat}
          onOpenModal={handleOpenModal}
          onArchiveSession={handleArchiveSession}
          onDeleteSession={handleDeleteSession}
        />

        {/* Main Content Area */}
        <div className={`flex-1 flex flex-col h-full min-w-0 overflow-hidden relative transition-[padding-left] duration-300 ${sidebarCollapsed ? "lg:pl-20" : "lg:pl-[18rem]"}`}>
          
          {/* Header Bar */}
          <ChatHeader
            activeSessionId={activeSessionId}
            onMenuToggle={() => setSidebarOpen(true)}
            onArchiveSession={handleArchiveSession}
            onDeleteSession={handleDeleteSession}
          />

          {/* Children Viewport */}
          <main className="flex-1 flex flex-col min-h-0 bg-dental-darkBg relative">
            {children}
          </main>
        </div>

        {/* Features Interactive Modals */}
        <FeatureModals 
          isOpen={activeModal !== null} 
          onClose={() => setActiveModal(null)} 
          activeModal={activeModal || ""} 
          onSendAttachedMessage={handleSendAttachedMessage}
        />
      </div>
    </ModalContext.Provider>
  );
}
