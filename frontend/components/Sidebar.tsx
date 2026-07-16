"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  Archive,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  Edit3,
  FolderOpen,
  LogOut,
  MessageSquare,
  MoreHorizontal,
  Pin,
  Rows3,
  Share2,
  Search,
  Settings,
  Sparkles,
  Star,
  Stethoscope,
  Trash2,
  X,
} from "lucide-react";
import type { ChatSession } from "@/lib/types";

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onOpenModal: (modalName: string) => void;
  onArchiveSession: (id: string) => Promise<void>;
  onDeleteSession: (id: string) => Promise<void>;
}

export function Sidebar({
  isOpen,
  onClose,
  isCollapsed,
  onToggleCollapse,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onOpenModal,
  onArchiveSession,
  onDeleteSession,
}: SidebarProps) {
  const router = useRouter();
  const { user, logout } = useAuth();
  const [searchQuery, setSearchQuery] = useState("");
  const [isSearchExpanded, setIsSearchExpanded] = useState(false);
  const [openActionMenuId, setOpenActionMenuId] = useState<string | null>(null);
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState<{ top: number; left: number } | null>(null);
  const [sidebarPrefs, setSidebarPrefs] = useState<{
    pinnedSessionIds: string[];
    hiddenSessionIds: string[];
    customTitles: Record<string, string>;
  }>({ pinnedSessionIds: [], hiddenSessionIds: [], customTitles: {} });
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const stored = window.localStorage.getItem("dental_ai_sidebar_prefs");
      if (stored) {
        const parsed = JSON.parse(stored) as Partial<typeof sidebarPrefs>;
        setSidebarPrefs({
          pinnedSessionIds: Array.isArray(parsed.pinnedSessionIds) ? parsed.pinnedSessionIds : [],
          hiddenSessionIds: Array.isArray(parsed.hiddenSessionIds) ? parsed.hiddenSessionIds : [],
          customTitles: parsed.customTitles && typeof parsed.customTitles === "object" ? parsed.customTitles : {},
        });
      }
    } catch {
      setSidebarPrefs({ pinnedSessionIds: [], hiddenSessionIds: [], customTitles: {} });
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("dental_ai_sidebar_prefs", JSON.stringify(sidebarPrefs));
  }, [sidebarPrefs]);

  useEffect(() => {
    if (!isOpen) {
      setOpenActionMenuId(null);
      setIsProfileMenuOpen(false);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isSearchExpanded || isCollapsed) return;
    searchInputRef.current?.focus();
  }, [isCollapsed, isSearchExpanded]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenActionMenuId(null);
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const initials = user?.full_name
    ? user.full_name.split(" ").map((n) => n[0]).join("").toUpperCase().substring(0, 2)
    : user?.email ? user.email.substring(0, 2).toUpperCase() : "DA";

  const normalizedQuery = searchQuery.trim().toLowerCase();

  const visibleSessions = useMemo(() => {
    return sessions
      .filter((session) => !sidebarPrefs.hiddenSessionIds.includes(session.id))
      .map((session) => ({
        ...session,
        title: sidebarPrefs.customTitles[session.id] || session.title || "Untitled chat",
      }))
      .sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime());
  }, [sessions, sidebarPrefs.customTitles, sidebarPrefs.hiddenSessionIds]);

  const matchedSessions = useMemo(() => {
    if (!normalizedQuery) return visibleSessions;
    return visibleSessions.filter((session) => {
      const messageText = session.messages.map((message) => message.content).join(" ").toLowerCase();
      return session.title.toLowerCase().includes(normalizedQuery) || messageText.includes(normalizedQuery);
    });
  }, [normalizedQuery, visibleSessions]);

  const pinnedSessions = useMemo(() => {
    const pinned = matchedSessions.filter((session) => sidebarPrefs.pinnedSessionIds.includes(session.id));
    return pinned.sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime());
  }, [matchedSessions, sidebarPrefs.pinnedSessionIds]);

  const recencyGroups = useMemo(() => {
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());

    const buckets = {
      today: [] as typeof matchedSessions,
      yesterday: [] as typeof matchedSessions,
      last7Days: [] as typeof matchedSessions,
      older: [] as typeof matchedSessions,
    };

    matchedSessions
      .filter((session) => !sidebarPrefs.pinnedSessionIds.includes(session.id))
      .forEach((session) => {
        const sessionDate = new Date(session.updated_at);
        const startOfSessionDay = new Date(sessionDate.getFullYear(), sessionDate.getMonth(), sessionDate.getDate());
        const dayDiff = Math.round((startOfToday.getTime() - startOfSessionDay.getTime()) / 86400000);

        if (dayDiff <= 0) {
          buckets.today.push(session);
        } else if (dayDiff === 1) {
          buckets.yesterday.push(session);
        } else if (dayDiff <= 7) {
          buckets.last7Days.push(session);
        } else {
          buckets.older.push(session);
        }
      });

    return buckets;
  }, [matchedSessions, sidebarPrefs.pinnedSessionIds]);

  function persistPrefs(updater: (current: typeof sidebarPrefs) => typeof sidebarPrefs) {
    setSidebarPrefs((current) => updater(current));
  }

  function handleSelect(sessionId: string) {
    onSelectSession(sessionId);
    onClose();
    setOpenActionMenuId(null);
  }

  function handleNewChatClick() {
    onNewChat();
    onClose();
    setOpenActionMenuId(null);
  }

  function togglePin(sessionId: string) {
    persistPrefs((current) => {
      const pinnedSessionIds = current.pinnedSessionIds.includes(sessionId)
        ? current.pinnedSessionIds.filter((id) => id !== sessionId)
        : [sessionId, ...current.pinnedSessionIds];
      return { ...current, pinnedSessionIds };
    });
  }

  function renameSession(sessionId: string, currentTitle: string) {
    const nextTitle = window.prompt("Rename chat", currentTitle)?.trim();
    if (!nextTitle) return;
    persistPrefs((current) => ({
      ...current,
      customTitles: { ...current.customTitles, [sessionId]: nextTitle },
    }));
  }

  async function archiveSessionAction(sessionId: string) {
    const confirmed = window.confirm("Archive this chat?");
    if (!confirmed) return;
    await onArchiveSession(sessionId);
    persistPrefs((current) => ({
      ...current,
      hiddenSessionIds: current.hiddenSessionIds.includes(sessionId)
        ? current.hiddenSessionIds
        : [...current.hiddenSessionIds, sessionId],
      pinnedSessionIds: current.pinnedSessionIds.filter((id) => id !== sessionId),
    }));
  }

  async function deleteSessionAction(sessionId: string) {
    const confirmed = window.confirm("Delete this chat permanently?");
    if (!confirmed) return;
    await onDeleteSession(sessionId);
    persistPrefs((current) => ({
      ...current,
      hiddenSessionIds: current.hiddenSessionIds.filter((id) => id !== sessionId),
      pinnedSessionIds: current.pinnedSessionIds.filter((id) => id !== sessionId),
      customTitles: Object.fromEntries(Object.entries(current.customTitles).filter(([id]) => id !== sessionId)),
    }));
  }

  const searchBarVisible = isSearchExpanded || normalizedQuery.length > 0;

  const compactModeClasses = isCollapsed ? "lg:w-20" : "lg:w-[18rem]";

  const actionButtonClass = "inline-flex h-8 w-8 items-center justify-center rounded-lg border border-transparent text-dental-textSecondary transition-all hover:bg-dental-border hover:text-dental-textPrimary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60 dark:text-white/75 dark:hover:bg-white/10 dark:hover:text-white";

  type NavItem = { icon: any; label: string; path?: string; modal?: string };
  const primaryLinks: NavItem[] = [
    { icon: Rows3, label: "Clinical library", modal: "library" },
    { icon: Clock3, label: "Appointments", path: "/appointments" },
    { icon: Stethoscope, label: "Dentists", path: "/dentists" },
  ];

  const accountLinks: NavItem[] = [
    { icon: MessageSquare, label: "Profile", path: "/profile" },
    { icon: Settings, label: "Settings", path: "/settings" },
    { icon: CircleHelp, label: "Help Center", path: "/help" },
  ];

  function renderSessionItem(session: ChatSession) {
    const displayTitle = session.title || "Untitled chat";
    const isActive = activeSessionId === session.id;
    const isPinned = sidebarPrefs.pinnedSessionIds.includes(session.id);
    const isMenuOpen = openActionMenuId === session.id;
    const sessionLink = typeof window === "undefined" ? "/chat" : `${window.location.origin}/chat?session_id=${session.id}`;

    const menuActions = [
      {
        key: "share",
        label: "Share",
        icon: Share2,
        onClick: async () => {
          if (typeof window === "undefined") return;
          try {
            if (navigator.share) {
              await navigator.share({ title: displayTitle, url: sessionLink });
            } else {
              await navigator.clipboard.writeText(sessionLink);
            }
          } finally {
            setOpenActionMenuId(null);
          }
        },
      },
      {
        key: "rename",
        label: "Rename",
        icon: Edit3,
        onClick: () => {
          renameSession(session.id, displayTitle);
          setOpenActionMenuId(null);
        },
      },
      {
        key: "pin",
        label: isPinned ? "Unpin" : "Pin chat",
        icon: Pin,
        onClick: () => {
          togglePin(session.id);
          setOpenActionMenuId(null);
        },
      },
      {
        key: "archive",
        label: "Archive",
        icon: Archive,
        onClick: async () => {
          await archiveSessionAction(session.id);
          setOpenActionMenuId(null);
        },
      },
      {
        key: "delete",
        label: "Delete",
        icon: Trash2,
        danger: true,
        onClick: async () => {
          await deleteSessionAction(session.id);
          setOpenActionMenuId(null);
        },
      },
    ] as const;

    return (
      <li
        key={session.id}
        className="group relative"
        onMouseEnter={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          setMenuPosition({ top: rect.top + rect.height / 2, left: rect.right + 8 });
        }}
      >
        <button
          type="button"
          onClick={() => handleSelect(session.id)}
          className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60 ${
            isCollapsed ? "justify-center" : "justify-start"
          } ${
            isActive
              ? "bg-dental-border text-dental-textPrimary dark:bg-white/12"
              : "text-dental-textSecondary hover:bg-dental-border hover:text-dental-textPrimary dark:hover:bg-white/10"
          }`}
          title={displayTitle}
        >
          <MessageSquare className={`h-4 w-4 shrink-0 ${isActive ? "text-dental-textPrimary" : "text-dental-textSecondary"}`} />
          {!isCollapsed && (
            <div className="min-w-0 flex-1 pr-20">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium leading-5">{displayTitle}</span>
                {isPinned && <Star className="h-3.5 w-3.5 shrink-0 fill-amber-400 text-amber-400" />}
              </div>
            </div>
          )}
        </button>

        <div
          className={`absolute right-1.5 top-1/2 z-30 -translate-y-1/2 flex items-center gap-0.5 rounded-xl border border-dental-border bg-dental-card p-1 shadow-xl transition-all duration-150 dark:border-white/10 dark:bg-[#2f2f2f] ${
            isMenuOpen
              ? "opacity-100 pointer-events-auto"
              : isCollapsed
                ? "opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto"
                : "opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto group-focus-within:opacity-100 group-focus-within:pointer-events-auto"
          }`}
        >
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              togglePin(session.id);
            }}
            className={actionButtonClass}
            aria-label={isPinned ? `Unpin ${displayTitle}` : `Pin ${displayTitle}`}
            title={isPinned ? "Unpin chat" : "Pin chat"}
          >
            <Pin className={`h-3.5 w-3.5 ${isPinned ? "text-amber-400" : ""}`} />
          </button>
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              const target = event.currentTarget.closest("li");
              if (target) {
                const rect = target.getBoundingClientRect();
                setMenuPosition({ top: rect.top + rect.height / 2, left: rect.right + 8 });
              }
              setOpenActionMenuId((current) => (current === session.id ? null : session.id));
            }}
            className={actionButtonClass}
            aria-label={`More actions for ${displayTitle}`}
            title="More actions"
          >
            <MoreHorizontal className="h-3.5 w-3.5" />
          </button>

          {isMenuOpen && menuPosition && typeof document !== "undefined" && createPortal(
            <div
              className="fixed z-[9999] w-72 overflow-hidden rounded-[1.35rem] border border-dental-border bg-dental-card p-3 shadow-2xl dark:border-white/10 dark:bg-[#333333]"
              style={{ top: `${menuPosition.top}px`, left: `${menuPosition.left}px`, transform: "translateY(-50%)" }}
            >
              {menuActions.map((item) => (
                (() => {
                  const isDanger = "danger" in item && item.danger;
                  const needsDivider = item.key === "pin" || item.key === "delete";
                  return (
                    <div key={item.key}>
                      {needsDivider && <div className="my-2 border-t border-white/15" />}
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          item.onClick();
                        }}
                        className={`flex w-full items-center gap-4 rounded-xl px-3 py-3 text-left text-[15px] transition-colors hover:bg-dental-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60 dark:hover:bg-white/10 ${
                          isDanger ? "text-red-500 hover:bg-red-500/10 dark:text-red-400" : "text-dental-textPrimary dark:text-white"
                        }`}
                      >
                        <item.icon className={`h-5 w-5 shrink-0 ${isDanger ? "" : "text-dental-textSecondary dark:text-white/85"}`} />
                        <span>{item.label}</span>
                      </button>
                    </div>
                  );
                })()
              ))}
            </div>,
            document.body,
          )}
        </div>
      </li>
    );
  }

  return (
    <>
      {/* Mobile Sidebar Overlay */}
      {isOpen && (
        <div 
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex h-full flex-col border-r border-dental-border bg-dental-sidebar shadow-2xl transition-all duration-300 ease-out lg:shadow-none dark:border-white/10 dark:bg-[#050505] ${compactModeClasses} ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        } lg:translate-x-0`}
      >
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className={`px-3 py-4 ${isCollapsed ? "space-y-4" : "space-y-4"}`}>
            <div className={`flex items-center gap-3 ${isCollapsed ? "justify-center" : "justify-between"}`}>
              <button
                type="button"
                onClick={() => {
                  if (isCollapsed) {
                    onToggleCollapse();
                    return;
                  }
                  onOpenModal("settings");
                  onClose();
                }}
                className={`flex items-center gap-3 rounded-xl px-2 py-1.5 text-left transition-colors hover:bg-dental-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60 dark:hover:bg-white/10 ${
                  isCollapsed ? "justify-center" : "min-w-0 flex-1"
                }`}
                aria-label={isCollapsed ? "Expand sidebar" : "DentalGPT home"}
                title={isCollapsed ? "Expand sidebar" : "DentalGPT"}
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-dental-border bg-dental-card shadow-sm dark:border-white/10 dark:bg-[#151515]">
                  <Image src="/chatbot-logo.svg" alt="DentalGPT logo" width={28} height={28} className="h-7 w-7 object-contain" priority />
                </div>
                {!isCollapsed && (
                  <div className="min-w-0">
                    <p className="truncate text-[1.35rem] font-extrabold tracking-tight text-dental-textPrimary dark:text-white">
                      DentalGPT
                    </p>
                  </div>
                )}
              </button>

              {!isCollapsed && (
                <button
                  type="button"
                  onClick={onToggleCollapse}
                  className="hidden h-10 w-10 items-center justify-center rounded-xl text-dental-textSecondary transition-all duration-200 hover:bg-dental-border hover:text-dental-textPrimary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60 lg:inline-flex dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white"
                  aria-label="Collapse sidebar"
                  title="Collapse sidebar"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
              )}
            </div>

            <div className={`flex items-center gap-3 ${isCollapsed ? "justify-center" : "justify-between"}`}>
              <button
                type="button"
                onClick={onClose}
                className="inline-flex h-10 w-10 items-center justify-center rounded-xl text-dental-textSecondary transition-all duration-200 hover:bg-dental-border hover:text-dental-textPrimary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60 lg:hidden dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white"
                aria-label="Close sidebar"
                title="Close sidebar"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="px-3 pb-2">
            <div className={`overflow-hidden transition-all duration-300 ease-out ${searchBarVisible && !isCollapsed ? "mb-2 max-h-20 opacity-100" : "max-h-0 opacity-0"}`}>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-dental-textSecondary" />
                <input
                  ref={searchInputRef}
                  type="search"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="Search by title or message"
                  className="w-full rounded-xl border border-dental-border bg-dental-card py-2.5 pl-9 pr-9 text-sm text-dental-textPrimary placeholder:text-dental-textSecondary transition-colors focus:border-dental-accent focus:outline-none dark:border-white/10 dark:bg-[#111111] dark:text-white dark:placeholder:text-white/45"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => setSearchQuery("")}
                    className="absolute right-2 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full text-dental-textSecondary transition-colors hover:bg-dental-card hover:text-dental-textPrimary"
                    aria-label="Clear search"
                    title="Clear search"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>
          </div>

          <nav className="scrollbar-hide flex-1 overflow-y-auto px-3 py-1">
            <div className="space-y-5">
              {normalizedQuery.length === 0 && (
                <section className="space-y-1">
                  <button
                    type="button"
                    onClick={handleNewChatClick}
                    className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] font-medium text-dental-textPrimary transition-all duration-150 hover:bg-dental-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60 dark:text-white dark:hover:bg-white/10 ${
                      isCollapsed ? "justify-center" : "justify-start"
                    }`}
                    aria-label="New chat"
                    title="New chat"
                  >
                    <Edit3 className="h-5 w-5 shrink-0" />
                    {!isCollapsed && <span>New chat</span>}
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      if (isCollapsed) {
                        onToggleCollapse();
                      }
                      setIsSearchExpanded(true);
                    }}
                    className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] font-medium text-dental-textPrimary transition-all duration-150 hover:bg-dental-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60 dark:text-white dark:hover:bg-white/10 ${
                      isCollapsed ? "justify-center" : "justify-start"
                    }`}
                    aria-label="Search chats"
                    title="Search chats"
                  >
                    <Search className="h-5 w-5 shrink-0" />
                    {!isCollapsed && <span>Search chats</span>}
                  </button>

                  {primaryLinks.map((item) => (
                    <button
                      key={item.label}
                      type="button"
                      onClick={() => {
                        if (item.path) {
                          router.push(item.path);
                        } else if (item.modal) {
                          onOpenModal(item.modal);
                        }
                        onClose();
                      }}
                      className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] font-medium text-dental-textPrimary transition-all duration-150 hover:bg-dental-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60 dark:text-white dark:hover:bg-white/10 ${
                        isCollapsed ? "justify-center" : "justify-start"
                      }`}
                      aria-label={item.label}
                      title={item.label}
                    >
                      <item.icon className="h-5 w-5 shrink-0" />
                      {!isCollapsed && <span className="truncate">{item.label}</span>}
                    </button>
                  ))}
                </section>
              )}

              {normalizedQuery.length > 0 && !isCollapsed && (
                <section className="space-y-2">
                  <p className={`px-1 pb-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-dental-textSecondary ${isCollapsed ? "lg:sr-only" : ""}`}>
                    Search results
                  </p>
                  {matchedSessions.length ? (
                    <ul className="space-y-1">{matchedSessions.map(renderSessionItem)}</ul>
                  ) : (
                    <p className="rounded-2xl border border-dashed border-dental-border px-3 py-4 text-sm text-dental-textSecondary">
                      No chats match this search.
                    </p>
                  )}
                </section>
              )}

              {normalizedQuery.length === 0 && !isCollapsed && pinnedSessions.length > 0 && (
                <section className="space-y-2">
                  <p className="px-3 text-base font-bold text-dental-textPrimary dark:text-white">Pinned</p>
                  <ul className="space-y-1">{pinnedSessions.map(renderSessionItem)}</ul>
                </section>
              )}

              {normalizedQuery.length === 0 && !isCollapsed && (
                <section className="space-y-2">
                  <p className="px-3 text-base font-bold text-dental-textPrimary dark:text-white">Recents</p>
                  <ul className="space-y-1">
                    {[
                      ...recencyGroups.today,
                      ...recencyGroups.yesterday,
                      ...recencyGroups.last7Days,
                      ...recencyGroups.older,
                    ].map(renderSessionItem)}
                  </ul>
                </section>
              )}

              {!normalizedQuery.length && !visibleSessions.length && !isCollapsed && (
                <div className="rounded-2xl border border-dashed border-dental-border px-3 py-4 text-sm text-dental-textSecondary">
                  No chats yet. Start a new consultation to build your history.
                </div>
              )}
            </div>
          </nav>

          <div className="border-t border-dental-border p-3 dark:border-white/10">
            <div className="relative">
              <button
                type="button"
                onClick={() => setIsProfileMenuOpen((current) => !current)}
                className={`flex w-full items-center gap-3 rounded-xl transition-all duration-150 hover:bg-dental-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60 dark:hover:bg-white/10 ${
                  isCollapsed ? "justify-center px-0 py-2" : "px-3 py-3"
                }`}
                aria-label="Account menu"
                title={user?.full_name || user?.email || "Dental AI user"}
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-orange-600 text-xs font-bold text-white shadow-sm">
                  {initials}
                </div>
                {!isCollapsed && (
                  <div className="min-w-0 flex-1 text-left">
                    <p className="truncate text-sm font-semibold text-dental-textPrimary dark:text-white">{user?.full_name || user?.email || "Dental AI user"}</p>
                    <p className="truncate text-xs text-dental-textSecondary">
                      {user?.role === "admin" ? "Admin account" : "Patient account"}
                    </p>
                  </div>
                )}
                {!isCollapsed && <FolderOpen className="h-4 w-4 shrink-0 text-dental-textSecondary dark:text-white/70" />}
              </button>

              {isProfileMenuOpen && (
                <div className={`absolute ${isCollapsed ? "left-14 bottom-0 w-72" : "left-0 right-0 bottom-full mb-2"} z-50 overflow-hidden rounded-[1.35rem] border border-dental-border bg-dental-card p-3 shadow-2xl dark:border-white/10 dark:bg-[#333333]`}>
                  <div className="mb-3 flex items-center gap-3 border-b border-dental-border px-2 pb-3 dark:border-white/10">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-orange-600 text-xs font-bold text-white">
                      {initials}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-dental-textPrimary dark:text-white">{user?.full_name || user?.email || "Dental AI user"}</p>
                      <p className="truncate text-xs text-dental-textSecondary dark:text-white/60">{user?.role === "admin" ? "Admin account" : "Patient account"}</p>
                    </div>
                    <ChevronRight className="h-4 w-4 text-dental-textSecondary dark:text-white/70" />
                  </div>

                  {accountLinks.map((item) => (
                    <button
                      key={item.label}
                      type="button"
                      onClick={() => {
                        if (item.path) {
                          router.push(item.path);
                        } else if (item.modal) {
                          onOpenModal(item.modal);
                        }
                        onClose();
                      }}
                      className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-[15px] text-dental-textPrimary transition-colors hover:bg-dental-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60 dark:text-white dark:hover:bg-white/10"
                    >
                      <item.icon className="h-5 w-5 shrink-0 text-dental-textSecondary dark:text-white/85" />
                      <span>{item.label}</span>
                    </button>
                  ))}

                  {user?.role === "admin" && (
                    <button
                      type="button"
                      onClick={() => {
                        onOpenModal("admin");
                        onClose();
                      }}
                      className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-[15px] text-red-300 transition-colors hover:bg-red-500/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/60"
                    >
                      <Settings className="h-5 w-5 shrink-0" />
                      <span>Admin workspace</span>
                    </button>
                  )}

                  <div className="my-2 border-t border-dental-border dark:border-white/10" />
                  <button
                    type="button"
                    onClick={() => {
                      logout();
                      router.replace("/login");
                    }}
                    className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-[15px] text-dental-textPrimary transition-colors hover:bg-dental-border dark:text-white dark:hover:bg-white/10"
                  >
                    <LogOut className="h-5 w-5 shrink-0 text-dental-textSecondary dark:text-white/85" />
                    <span>Log out</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
