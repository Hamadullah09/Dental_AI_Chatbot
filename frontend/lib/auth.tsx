"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getCurrentUser } from "./api";
import type { AuthResponse, User } from "./types";

type AuthContextValue = {
  user: User | null;
  token: string | null;
  isReady: boolean;
  saveAuth: (auth: AuthResponse) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function hydrateAuth() {
      try {
        const storedToken = localStorage.getItem("dental_ai_token");
        if (!storedToken) return;

        const storedUser = localStorage.getItem("dental_ai_user");
        if (storedUser) {
          try {
            const parsed = JSON.parse(storedUser) as User;
            if (!cancelled) {
              setUser(parsed);
            }
          } catch {
            localStorage.removeItem("dental_ai_user");
          }
        }

        if (!cancelled) {
          setToken(storedToken);
        }

        const verifiedUser = await getCurrentUser(storedToken);
        if (!cancelled) {
          setUser(verifiedUser);
          localStorage.setItem("dental_ai_user", JSON.stringify(verifiedUser));
        }
      } catch {
        localStorage.removeItem("dental_ai_token");
        localStorage.removeItem("dental_ai_user");
        if (!cancelled) {
          setToken(null);
          setUser(null);
        }
      } finally {
        if (!cancelled) {
          setIsReady(true);
        }
      }
    }

    hydrateAuth();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    function handleAuthExpired() {
      setToken(null);
      setUser(null);
    }

    window.addEventListener("dental_ai_auth_expired", handleAuthExpired);
    return () => window.removeEventListener("dental_ai_auth_expired", handleAuthExpired);
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    token,
    isReady,
    saveAuth(auth) {
      setToken(auth.access_token);
      setUser(auth.user);
      localStorage.setItem("dental_ai_token", auth.access_token);
      localStorage.setItem("dental_ai_user", JSON.stringify(auth.user));
    },
    logout() {
      setToken(null);
      setUser(null);
      localStorage.removeItem("dental_ai_token");
      localStorage.removeItem("dental_ai_user");
    }
  }), [isReady, token, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
