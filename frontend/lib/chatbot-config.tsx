"use client";

import { createContext, useContext, useEffect, useState } from "react";

export interface ChatbotConfig {
  chatbot_name: string;
  chatbot_tagline: string;
  welcome_message: string;
  input_placeholder: string;
  suggested_questions: string[];
  disclaimer_banner: string;
  typing_message: string;
  searching_message: string;
  generating_message: string;
  error_message: string;
  network_error_message: string;
  rate_limit_message: string;
  empty_message: string;
  no_sources_message: string;
  thinking_messages: string[];
  export_filename_prefix: string;
  medical_disclaimer: string;
  max_upload_mb: number;
  streaming_enabled: boolean;
  enable_web_search: boolean;
  enable_multimodal_rag: boolean;
  rate_limit_chat_per_minute: number;
}

const defaultConfig: ChatbotConfig = {
  chatbot_name: "DentalGPT",
  chatbot_tagline: "Your AI-powered dental health assistant",
  welcome_message: "How can I help?",
  input_placeholder: "Ask anything about dental care...",
  suggested_questions: [
    "What is tooth decay?",
    "Explain gingivitis in simple words",
    "How often should I visit the dentist?",
    "What are the signs of oral cancer?",
  ],
  disclaimer_banner: "Dental AI is for education and clinical decision support only.",
  typing_message: "Thinking...",
  searching_message: "Searching knowledge base...",
  generating_message: "Generating answer...",
  error_message: "Something went wrong. Please try again.",
  network_error_message: "Could not reach the server. Please check your connection.",
  rate_limit_message: "Too many requests. Please wait a moment and try again.",
  empty_message: "Please enter a question.",
  no_sources_message: "No sources found for this query.",
  thinking_messages: ["Searching knowledge base...", "Analyzing your question...", "Finding relevant information..."],
  export_filename_prefix: "dental-chat",
  medical_disclaimer: "Dental AI is for education and clinical decision support only.",
  max_upload_mb: 200,
  streaming_enabled: true,
  enable_web_search: false,
  enable_multimodal_rag: true,
  rate_limit_chat_per_minute: 20,
};

const ChatbotConfigContext = createContext<ChatbotConfig>(defaultConfig);

export function useChatbotConfig() {
  return useContext(ChatbotConfigContext);
}

export function ChatbotConfigProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<ChatbotConfig>(defaultConfig);

  useEffect(() => {
    const apiBase = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
    fetch(`${apiBase}/api/config`)
      .then((res) => res.json())
      .then((data) => {
        if (data && data.chatbot_name) {
          setConfig(data);
        }
      })
      .catch(() => {});
  }, []);

  return (
    <ChatbotConfigContext.Provider value={config}>
      {children}
    </ChatbotConfigContext.Provider>
  );
}
