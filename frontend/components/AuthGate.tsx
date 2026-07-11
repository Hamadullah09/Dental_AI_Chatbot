"use client";

import { useEffect } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export function AuthGate({ children, adminOnly = false }: {
  children: ReactNode;
  adminOnly?: boolean;
}) {
  const router = useRouter();
  const { user, token, isReady } = useAuth();

  useEffect(() => {
    if (!isReady) return;
    if (!token) {
      router.replace("/login");
      const fallbackRedirect = window.setTimeout(() => {
        if (window.location.pathname !== "/login") {
          window.location.replace("/login");
        }
      }, 1200);
      return () => window.clearTimeout(fallbackRedirect);
    }
    if (adminOnly && user?.role !== "admin") {
      router.replace("/chat");
      const fallbackRedirect = window.setTimeout(() => {
        if (window.location.pathname !== "/chat") {
          window.location.replace("/chat");
        }
      }, 1200);
      return () => window.clearTimeout(fallbackRedirect);
    }
  }, [adminOnly, isReady, router, token, user]);

  if (!isReady || !token || (adminOnly && user?.role !== "admin")) {
    const loadingText = !isReady
      ? "Preparing workspace"
      : !token
        ? "Redirecting to sign in"
        : "Checking access";

    return (
      <main className="flex min-h-dvh w-screen items-center justify-center bg-dental-darkBg px-6 text-dental-textPrimary">
        <div className="flex w-full max-w-sm flex-col items-center text-center fade-in">
          <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl border border-dental-border bg-dental-card shadow-lg">
            <span className="text-xl font-extrabold text-dental-accent">DG</span>
          </div>
          <h1 className="text-xl font-semibold tracking-tight">DentalGPT</h1>
          <p className="mt-2 text-sm text-dental-textSecondary">{loadingText}</p>
          <div className="mt-6 h-1.5 w-full overflow-hidden rounded-full bg-dental-border">
            <div className="dental-loading-slider h-full w-1/3 rounded-full bg-dental-accent" />
          </div>
        </div>
      </main>
    );
  }

  return <>{children}</>;
}
