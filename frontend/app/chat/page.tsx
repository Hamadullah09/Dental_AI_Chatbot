"use client";

import React, { FormEvent, useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { AppShell, useModal } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { ChatWindow } from "@/components/ChatWindow";
import { ChatInput } from "@/components/ChatInput";
import { getChatDocument, sendChat, uploadChatDocument } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DocumentItem, Message } from "@/lib/types";

function ChatContent() {
  const { token } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlSessionId = searchParams.get("session_id");

  const { sessions, refreshSessions, openModal } = useModal();

  const [question, setQuestion] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [uploadProgress, setUploadProgress] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [attachment, setAttachment] = useState<File | null>(null);
  const [activeDocument, setActiveDocument] = useState<DocumentItem | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [searchWeb, setSearchWeb] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatWindowRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);
  const loadedSessionRef = useRef<string | null>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  useEffect(() => {
    if (!toast || isLoading) return;
    const timeoutId = window.setTimeout(() => setToast(""), 5000);
    return () => window.clearTimeout(timeoutId);
  }, [toast, isLoading]);

  // Load session from urlSessionId or sessions list
  useEffect(() => {
    if (urlSessionId) {
      const session = sessions.find((s) => s.id === urlSessionId);
      if (session && loadedSessionRef.current !== session.id) {
        loadedSessionRef.current = session.id;
        setSessionId(session.id);
        setMessages(session.messages);
      }
    } else {
      loadedSessionRef.current = null;
      setSessionId(null);
      setMessages([]);
    }
  }, [urlSessionId, sessions]);

  // Check if there are queued attachment actions from other overlays
  useEffect(() => {
    const handleAttachedSend = () => {
      const filename = localStorage.getItem("dental_ai_attached_file");
      const prompt = localStorage.getItem("dental_ai_attached_prompt");
      if (prompt) {
        localStorage.removeItem("dental_ai_attached_file");
        localStorage.removeItem("dental_ai_attached_prompt");
        handleQuickAction(prompt, filename || undefined);
      }
    };
    window.addEventListener("dental_ai_trigger_attachment_send", handleAttachedSend);
    return () => window.removeEventListener("dental_ai_trigger_attachment_send", handleAttachedSend);
  }, [sessions]);

  async function waitForDocumentReady(documentId: string) {
    if (!token) throw new Error("Please sign in again.");
    for (let attempt = 0; attempt < 180; attempt += 1) {
      const doc = await getChatDocument(documentId, token);
      setActiveDocument(doc);
      setUploadProgress(`${doc.ingestion_step || "Processing PDF"} (${doc.ingestion_progress || 0}%)`);
      if (doc.status === "ready") return doc;
      if (doc.status === "failed") {
        throw new Error(doc.error_message || "Document ingestion failed.");
      }
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
    }
    throw new Error("Document is still processing. Please try again shortly.");
  }

  async function submitPrompt(promptText: string, fileToUpload: File | null = null) {
    if (!token || (!promptText.trim() && !fileToUpload)) return;
    let scopedDocument = activeDocument;
    const prompt = promptText.trim() || "Summarize this uploaded dental document and answer using only this document.";

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: fileToUpload ? `Attached PDF: ${fileToUpload.name}\n\n${prompt}` : prompt,
      sources: [],
      visuals: [],
      created_at: new Date().toISOString()
    };

    setMessages((current) => [...current, userMessage]);
    setQuestion("");
    setError("");
    setToast("");
    setIsLoading(true);

    try {
      if (fileToUpload) {
        setUploadProgress("Uploading PDF for grounded chat...");
        const uploaded = await uploadChatDocument(fileToUpload, token);
        setAttachment(null);
        scopedDocument = await waitForDocumentReady(uploaded.id);
        setUploadProgress("");
      }

      const response = await sendChat({
        question: prompt,
        session_id: sessionId,
        document_id: scopedDocument?.id || null,
        search_web: searchWeb
      }, token);
      
      // If we created a new session, update search params to sync the URL
      if (!sessionId && response.session_id) {
        loadedSessionRef.current = response.session_id;
        router.push(`/chat?session_id=${response.session_id}`);
      }

      setSessionId(response.session_id);
      setMessages((current) => [
        ...current,
        {
          id: response.message_id,
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          visuals: response.visuals || [],
          created_at: new Date().toISOString()
        }
      ]);
      await refreshSessions();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Chat request failed");
    } finally {
      setIsLoading(false);
    }
  }

  // Handle regular chat form submissions
  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    await submitPrompt(question, attachment);
  }

  // Handle quick action clicks
  const handleQuickAction = async (actionText: string, mockFilename?: string) => {
    if (mockFilename) {
      setToast(`Attach ${mockFilename} and send the prompt to analyze it safely.`);
      return;
    }

    setQuestion(actionText);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const nextFile = e.target.files[0];
      if (nextFile.type !== "application/pdf" && !nextFile.name.toLowerCase().endsWith(".pdf")) {
        setError("Please upload a PDF file.");
        return;
      }
      setAttachment(nextFile);
    }
  };

  function toggleVoiceInput() {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setToast("Voice input is not supported in this browser. Try Chrome or Edge.");
      return;
    }
    if (isListening && recognitionRef.current) {
      recognitionRef.current.stop();
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.onstart = () => {
      setIsListening(true);
      setToast("Listening...");
    };
    recognition.onresult = (event: any) => {
      const transcript = Array.from(event.results)
        .map((result: any) => result[0]?.transcript || "")
        .join(" ")
        .trim();
      if (transcript) {
        setQuestion(transcript);
      }
    };
    recognition.onerror = () => {
      setError("Could not access microphone. Please allow microphone permission.");
      setIsListening(false);
    };
    recognition.onend = () => {
      setIsListening(false);
      setToast("Voice converted to text.");
    };
    recognitionRef.current = recognition;
    recognition.start();
  }

  return (
    <section className="flex-1 flex flex-col h-full overflow-hidden bg-dental-darkBg relative">
      {/* Scrollable messages area */}
      <ChatWindow 
        messages={messages}
        isLoading={isLoading}
        onQuickAction={handleQuickAction}
        onOpenModal={openModal}
        onTriggerFileUpload={() => fileInputRef.current?.click()}
        onStatus={setToast}
        onRetryMessage={(retryQuestion) => submitPrompt(retryQuestion, null)}
        chatWindowRef={chatWindowRef}
        bottomRef={bottomRef}
      />

      {/* Input composition area */}
      <ChatInput 
        value={question}
        onChange={setQuestion}
        onSubmit={onSubmit}
        isLoading={isLoading}
        fileInputRef={fileInputRef}
        onFileChange={handleFileChange}
        attachment={attachment}
        onRemoveAttachment={() => setAttachment(null)}
        activeDocument={activeDocument}
        onClearActiveDocument={() => {
          setActiveDocument(null);
        }}
        isListening={isListening}
        onToggleVoice={toggleVoiceInput}
        searchWeb={searchWeb}
        onToggleSearchWeb={() => setSearchWeb((current) => !current)}
      />

      {isListening && (
        <div className="absolute bottom-24 left-1/2 -translate-x-1/2 z-30 w-[min(92vw,420px)] rounded-2xl border border-red-400/30 bg-dental-card/95 px-5 py-4 shadow-2xl">
          <div className="flex items-center gap-3 min-w-0">
            <div className="relative h-11 w-11 rounded-full bg-red-500 flex items-center justify-center text-white">
              <span className="absolute h-11 w-11 rounded-full bg-red-400/30 animate-ping" />
              <span className="relative h-3 w-3 rounded-full bg-white" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-bold text-dental-textPrimary">Listening</p>
              <p className="text-[11px] text-dental-textSecondary truncate">
                Speak now. Tap the mic control again to stop.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Floating status bar */}
      {(toast || error || uploadProgress) && (
        <div className={`absolute top-2 left-1/2 -translate-x-1/2 px-4 py-1.5 border rounded-full text-[10px] max-w-md text-center shadow-lg pointer-events-none z-20 ${
          error
            ? "border-red-500/30 bg-red-500/10 text-red-500"
            : "border-dental-border bg-dental-card/90 text-dental-textSecondary"
        }`}>
          {error || uploadProgress || toast}
        </div>
      )}
    </section>
  );
}

export default function ChatPage() {
  return (
    <AuthGate>
      <AppShell title="Dental Chat" subtitle="Ask questions grounded in uploaded dental PDFs.">
        <Suspense
          fallback={
            <div className="flex flex-1 items-center justify-center bg-dental-darkBg px-6 text-dental-textPrimary">
              <div className="flex w-full max-w-sm flex-col items-center text-center fade-in">
                <h1 className="text-xl font-semibold tracking-tight">Loading chat</h1>
                <p className="mt-2 text-sm text-dental-textSecondary">Preparing your DentalGPT workspace</p>
                <div className="mt-6 h-1.5 w-full overflow-hidden rounded-full bg-dental-border">
                  <div className="dental-loading-slider h-full w-1/3 rounded-full bg-dental-accent" />
                </div>
              </div>
            </div>
          }
        >
          <ChatContent />
        </Suspense>
      </AppShell>
    </AuthGate>
  );
}
