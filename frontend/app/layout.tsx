import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Providers } from "@/components/Providers";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ChatbotConfigProvider } from "@/lib/chatbot-config";
import "./globals.css";

export const metadata: Metadata = {
  title: "Dental AI Chatbot",
  description: "Enterprise-grade dental RAG chatbot powered by AI",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
    apple: "/chatbot-logo.svg",
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ErrorBoundary>
          <ChatbotConfigProvider>
            <Providers>{children}</Providers>
          </ChatbotConfigProvider>
        </ErrorBoundary>
      </body>
    </html>
  );
}
