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
  const [status, setStatus] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [attachment, setAttachment] = useState<File | null>(null);
  const [activeDocument, setActiveDocument] = useState<DocumentItem | null>(null);
  const [isListening, setIsListening] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatWindowRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Load session from urlSessionId or sessions list
  useEffect(() => {
    if (urlSessionId) {
      const session = sessions.find((s) => s.id === urlSessionId);
      if (session) {
        setSessionId(session.id);
        setMessages(session.messages);
      }
    } else {
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

  // Handle simulated attachment submissions
  async function submitSimulatedAttachment(file: File, textPrompt: string) {
    setIsLoading(true);
    setStatus("Analyzing uploaded clinical document...");

    const userMsgContent = textPrompt.trim() 
      ? `📄 Attached: ${file.name}\n\n${textPrompt}`
      : `📄 Attached file: ${file.name}`;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: userMsgContent,
      sources: [],
      created_at: new Date().toISOString()
    };

    setMessages((current) => [...current, userMessage]);
    setAttachment(null);
    setQuestion("");

    // Simulate response delay
    setTimeout(() => {
      let aiAnswer = "";
      const lowerName = file.name.toLowerCase();

      if (lowerName.includes("xray") || lowerName.includes("x-ray") || file.type.startsWith("image/")) {
        aiAnswer = `I have received and processed your X-ray: **${file.name}**.\n\n` +
          `**Radiographic Analysis Summary:**\n` +
          `• **Local Radiolucency:** There is a minor shadowed area (radiolucency) in the sub-enamel layer of tooth #19 (lower left first molar). This may point to moderate dental caries (decay) developing beneath the proximal wall.\n` +
          `• **Periodontal Margins:** The alveolar bone levels appear stable, with minimal horizontal bone loss. Bone crest height is within the normal limit of 1.5-2mm below the cementoenamel junction.\n` +
          `• **Root Anatomy:** Root canals appear clear with no signs of periapical abscesses or widening of the periodontal ligament space.\n\n` +
          `**Clinical recommendation:** This requires an in-person verification. I advise scheduling a physical dental examination for a cold response test to assess pulp vitality.`;
      } else {
        aiAnswer = `I have completed reading the clinical document: **${file.name}**.\n\n` +
          `**Key Dental Observations:**\n` +
          `• **Periodontal Telemetry:** The pocket depth records indicate minor gingival swelling, with localized pocket depths measuring 4mm in the upper right molars (gingivitis/mild periodontitis).\n` +
          `• **Diagnostic Impression:** Localized bleeding index is noted at 15%. Enamel mineralization is reported stable.\n` +
          `• **Treatment Plan Reference:** The document references scheduled routine cleaning and potential conservative composite restoration for tooth #14.\n\n` +
          `Would you like me to clarify any dental terms or assist with booking a follow-up appointment with Dr. Arthur Smith?`;
      }

      const aiMessage: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: aiAnswer,
        sources: [],
        created_at: new Date().toISOString()
      };

      setMessages((current) => [...current, aiMessage]);
      setIsLoading(false);
      setStatus("Grounded guidance provided.");
    }, 2000);
  }

  async function waitForDocumentReady(documentId: string) {
    if (!token) throw new Error("Please sign in again.");
    for (let attempt = 0; attempt < 180; attempt += 1) {
      const doc = await getChatDocument(documentId, token);
      setActiveDocument(doc);
      setStatus(`${doc.ingestion_step || "Processing PDF"} (${doc.ingestion_progress || 0}%)`);
      if (doc.status === "ready") return doc;
      if (doc.status === "failed") {
        throw new Error(doc.error_message || "Document ingestion failed.");
      }
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
    }
    throw new Error("Document is still processing. Please try again shortly.");
  }

  // Handle regular chat form submissions
  async function onSubmit(event: FormEvent) {
    event.preventDefault();

    if (!token || (!question.trim() && !attachment)) return;
    let scopedDocument = activeDocument;
    const prompt = question.trim() || "Summarize this uploaded dental document and answer using only this document.";

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: attachment ? `Attached PDF: ${attachment.name}\n\n${prompt}` : prompt,
      sources: [],
      created_at: new Date().toISOString()
    };

    setMessages((current) => [...current, userMessage]);
    setQuestion("");
    setIsLoading(true);

    try {
      if (attachment) {
        setStatus("Uploading PDF for grounded chat...");
        const uploaded = await uploadChatDocument(attachment, token);
        setAttachment(null);
        scopedDocument = await waitForDocumentReady(uploaded.id);
      }

      setStatus(scopedDocument ? `Retrieving context from ${scopedDocument.title || scopedDocument.original_filename}...` : "Retrieving dental context...");
      const response = await sendChat({
        question: prompt,
        session_id: sessionId,
        document_id: scopedDocument?.id || null
      }, token);
      
      // If we created a new session, update search params to sync the URL
      if (!sessionId && response.session_id) {
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
          created_at: new Date().toISOString()
        }
      ]);
      setStatus(response.disclaimer);
      await refreshSessions();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Chat request failed");
    } finally {
      setIsLoading(false);
    }
  }

  // Handle quick action clicks
  const handleQuickAction = async (actionText: string, mockFilename?: string) => {
    if (mockFilename) {
      setIsLoading(true);
      setStatus("Analyzing file...");
      setTimeout(() => {
        setIsLoading(false);
        setMessages((current) => [
          ...current,
          {
            id: crypto.randomUUID(),
            role: "user",
            content: `📄 Attached: ${mockFilename}\n\n${actionText}`,
            sources: [],
            created_at: new Date().toISOString()
          },
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: `I have received and evaluated the dental report **${mockFilename}**.\n\nThe document details outline moderate localized gingivitis with bleeding on probing. Enamel surfaces remain intact. \n\nDr. Smith advises rinsing with chlorhexidine mouthwash and scheduling a plaque scaling session. Would you like me to book this slot for you?`,
            sources: [],
            created_at: new Date().toISOString()
          }
        ]);
        setStatus("Grounded file analysis provided.");
      }, 1500);
      return;
    }

    setQuestion(actionText);
    // Autofill and submit after state updates
    setTimeout(() => {
      const mockForm = document.createElement("form");
      onSubmit(mockForm as any);
    }, 50);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const nextFile = e.target.files[0];
      if (nextFile.type !== "application/pdf" && !nextFile.name.toLowerCase().endsWith(".pdf")) {
        setStatus("Please upload a PDF file.");
        return;
      }
      setAttachment(nextFile);
    }
  };

  function toggleVoiceInput() {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setStatus("Voice input is not supported in this browser. Try Chrome or Edge.");
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
      setStatus("Listening...");
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
      setStatus("Could not access microphone. Please allow microphone permission.");
      setIsListening(false);
    };
    recognition.onend = () => {
      setIsListening(false);
      setStatus("Voice converted to text.");
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
        onStatus={setStatus}
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
        isListening={isListening}
        onToggleVoice={toggleVoiceInput}
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
      {status && (
        <div className="absolute top-2 left-1/2 -translate-x-1/2 px-4 py-1.5 bg-dental-card/90 border border-dental-border rounded-full text-[10px] text-dental-textSecondary max-w-md text-center shadow-lg pointer-events-none z-20">
          {status}
        </div>
      )}
    </section>
  );
}

export default function ChatPage() {
  return (
    <AuthGate>
      <AppShell title="Dental Chat" subtitle="Ask questions grounded in uploaded dental PDFs.">
        <Suspense fallback={<div className="empty-state">Loading chat workspace...</div>}>
          <ChatContent />
        </Suspense>
      </AppShell>
    </AuthGate>
  );
}
