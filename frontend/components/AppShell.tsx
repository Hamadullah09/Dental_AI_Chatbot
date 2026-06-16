"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { BookOpen, FileText, History, LogIn, LogOut, MessageSquare, Moon, Shield, Sun } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";

const navItems = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/history", label: "History", icon: History },
  { href: "/admin", label: "Admin", icon: Shield }
];

export function AppShell({ title, subtitle, children }: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" href="/chat">
          <span className="brand-mark"><BookOpen size={18} /></span>
          <span>Dental AI</span>
        </Link>

        <nav className="nav-group">
          {navItems.map((item) => {
            const Icon = item.icon;
            if (item.href === "/admin" && user?.role !== "admin") {
              return null;
            }
            return (
              <Link
                key={item.href}
                className={`nav-link ${pathname === item.href ? "active" : ""}`}
                href={item.href}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <button className="side-action" onClick={toggleTheme}>
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
          </button>

          {user ? (
            <>
              <div className="user-chip">
                <strong>{user.full_name || user.email}</strong>
                <span>{user.role}</span>
              </div>
              <button className="side-action" onClick={handleLogout}>
                <LogOut size={18} />
                <span>Sign out</span>
              </button>
            </>
          ) : (
            <Link className="side-action" href="/login">
              <LogIn size={18} />
              <span>Sign in</span>
            </Link>
          )}
        </div>
      </aside>

      <main className="page">
        <header className="topbar">
          <div>
            <h1>{title}</h1>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          <button className="button secondary" onClick={toggleTheme}>
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            <span>{theme === "dark" ? "Light" : "Dark"}</span>
          </button>
        </header>
        {children}
      </main>
    </div>
  );
}
