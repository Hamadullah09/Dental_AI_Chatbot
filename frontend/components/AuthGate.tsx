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
      return;
    }
    if (adminOnly && user?.role !== "admin") {
      router.replace("/chat");
    }
  }, [adminOnly, isReady, router, token, user]);

  if (!isReady || !token || (adminOnly && user?.role !== "admin")) {
    return <div className="empty-state">Loading workspace...</div>;
  }

  return <>{children}</>;
}
