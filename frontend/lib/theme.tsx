"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Theme = "light" | "dark";

type ThemeContextValue = {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const stored = localStorage.getItem("dental_ai_theme") as Theme | null;
    const nextTheme = stored || "light";
    setTheme(nextTheme);
    document.documentElement.dataset.theme = nextTheme;
  }, []);

  const value = useMemo(() => ({
    theme,
    setTheme(t: Theme) {
      setTheme(t);
      localStorage.setItem("dental_ai_theme", t);
      document.documentElement.dataset.theme = t;
    },
    toggleTheme() {
      const nextTheme = theme === "dark" ? "light" : "dark";
      setTheme(nextTheme);
      localStorage.setItem("dental_ai_theme", nextTheme);
      document.documentElement.dataset.theme = nextTheme;
    }
  }), [theme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used inside ThemeProvider");
  }
  return context;
}
