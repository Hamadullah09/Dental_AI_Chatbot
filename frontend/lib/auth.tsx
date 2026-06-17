"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
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
    setToken(localStorage.getItem("dental_ai_token"));
    const storedUser = localStorage.getItem("dental_ai_user");
    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
    setIsReady(true);
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
