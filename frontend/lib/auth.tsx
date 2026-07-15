"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getCurrentUser } from "./api";
import type { AuthResponse, User } from "./types";

type AuthContextValue = {
  user: User | null;
  token: string | null;
  refreshToken: string | null;
  isReady: boolean;
  saveAuth: (auth: AuthResponse) => void;
  logout: () => void;
  refreshAccessToken: () => Promise<boolean>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = "dental_ai_token";
const REFRESH_TOKEN_KEY = "dental_ai_refresh_token";
const USER_KEY = "dental_ai_user";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);

  const refreshAccessToken = useCallback(async (): Promise<boolean> => {
    const storedRefresh = refreshToken || (typeof window !== "undefined" ? localStorage.getItem(REFRESH_TOKEN_KEY) : null);
    if (!storedRefresh) return false;

    try {
      const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
      const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: storedRefresh }),
      });

      if (!response.ok) return false;

      const data = await response.json();
      setToken(data.access_token);
      setRefreshToken(data.refresh_token);
      setUser(data.user);
      localStorage.setItem(TOKEN_KEY, data.access_token);
      localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
      localStorage.setItem(USER_KEY, JSON.stringify(data.user));
      return true;
    } catch {
      return false;
    }
  }, [refreshToken]);

  useEffect(() => {
    let cancelled = false;

    async function hydrateAuth() {
      try {
        const storedToken = localStorage.getItem(TOKEN_KEY);
        const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
        if (!storedToken) return;

        const storedUser = localStorage.getItem(USER_KEY);
        if (storedUser) {
          try {
            const parsed = JSON.parse(storedUser) as User;
            if (!cancelled) {
              setUser(parsed);
              setToken(storedToken);
              setRefreshToken(storedRefreshToken);
            }
          } catch {
            localStorage.removeItem(USER_KEY);
          }
        }

        if (!cancelled) {
          setToken(storedToken);
          setRefreshToken(storedRefreshToken);
        }

        const verifiedUser = await getCurrentUser(storedToken);
        if (!cancelled) {
          setUser(verifiedUser);
          localStorage.setItem(USER_KEY, JSON.stringify(verifiedUser));
        }
      } catch {
        const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
        if (storedRefreshToken) {
          const refreshed = await refreshAccessToken();
          if (!cancelled && !refreshed) {
            localStorage.removeItem(TOKEN_KEY);
            localStorage.removeItem(REFRESH_TOKEN_KEY);
            localStorage.removeItem(USER_KEY);
            setToken(null);
            setRefreshToken(null);
            setUser(null);
          }
        } else {
          localStorage.removeItem(TOKEN_KEY);
          localStorage.removeItem(REFRESH_TOKEN_KEY);
          localStorage.removeItem(USER_KEY);
          if (!cancelled) {
            setToken(null);
            setRefreshToken(null);
            setUser(null);
          }
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
  }, [refreshAccessToken]);

  useEffect(() => {
    function handleAuthExpired() {
      setToken(null);
      setRefreshToken(null);
      setUser(null);
    }

    window.addEventListener("dental_ai_auth_expired", handleAuthExpired);
    return () => window.removeEventListener("dental_ai_auth_expired", handleAuthExpired);
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    token,
    refreshToken,
    isReady,
    saveAuth(auth) {
      setToken(auth.access_token);
      setRefreshToken(auth.refresh_token || null);
      setUser(auth.user);
      localStorage.setItem(TOKEN_KEY, auth.access_token);
      if (auth.refresh_token) {
        localStorage.setItem(REFRESH_TOKEN_KEY, auth.refresh_token);
      }
      localStorage.setItem(USER_KEY, JSON.stringify(auth.user));
    },
    logout() {
      setToken(null);
      setRefreshToken(null);
      setUser(null);
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    },
    refreshAccessToken,
  }), [isReady, token, refreshToken, user, refreshAccessToken]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
