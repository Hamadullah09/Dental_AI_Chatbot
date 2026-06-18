"use client";

import React from "react";
import { Tooth } from "lucide-react";
import type { Message } from "@/lib/types";
import { MessageBubble } from "./MessageBubble";
import { QuickActions } from "./QuickActions";

interface ChatWindowProps {
  messages: Message[];
  isLoading: boolean;
  onQuickAction: (actionText: string) => void;
  onOpenModal: (modalName: string) => void;
  onTriggerFileUpload: () => void;
  onStatus: (status: string) => void;
  chatWindowRef: React.RefObject<HTMLDivElement>;
  bottomRef: React.RefObject<HTMLDivElement>;
}

export function ChatWindow({
  messages,
  isLoading,
  onQuickAction,
  onOpenModal,
  onTriggerFileUpload,
  onStatus,
  chatWindowRef,
  bottomRef,
}: ChatWindowProps) {
  const isChatEmpty = messages.length === 0;

  return (
    <div 
      ref={chatWindowRef}
      className="flex-1 overflow-y-auto p-4 md:p-8 scroll-smooth"
    >
      <div className="max-w-3xl mx-auto h-full flex flex-col justify-between">
        
        {isChatEmpty ? (
          /* Welcome Screen (Empty State) */
          <div className="flex-1 flex flex-col justify-center items-center text-center space-y-6 my-auto py-10 fade-in">
            
            <div className="space-y-2">
              <h1 className="text-3xl font-bold text-white">How can I help with your dental care today?</h1>
              <p className="text-gray-400 max-w-md mx-auto text-sm leading-relaxed">
                AI-powered assistance for symptoms, appointments, and understanding your X-rays.
              </p>
            </div>

            {/* Quick Actions component */}
            <QuickActions 
              onQuickAction={onQuickAction}
              onOpenModal={onOpenModal}
              onTriggerFileUpload={onTriggerFileUpload}
            />
          </div>
        ) : (
          /* Active Chat Conversation View */
          <div className="flex flex-col space-y-6 pb-20 w-full">
            {messages.map((message) => (
              <MessageBubble 
                key={message.id} 
                message={message} 
                onStatus={onStatus} 
              />
            ))}

            {/* Typing Indicator */}
            {isLoading && (
              <div id="typingIndicator" className="flex gap-4 fade-in">
                <div className="w-8 h-8 rounded-full bg-dental-card border border-dental-border flex items-center justify-center text-dental-accent shrink-0">
                  <Tooth className="w-4 h-4" />
                </div>
                <div className="bg-dental-card border border-dental-border rounded-2xl rounded-tl-sm px-4 py-3.5 flex items-center gap-1 h-10">
                  <div className="w-2 h-2 bg-gray-400 rounded-full typing-dot"></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full typing-dot"></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full typing-dot"></div>
                </div>
              </div>
            )}
            
            <div ref={bottomRef} />
          </div>
        )}

      </div>
    </div>
  );
}
