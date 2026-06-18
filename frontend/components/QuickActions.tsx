"use client";

import { Activity, CalendarPlus, UploadCloud, Sparkles } from "lucide-react";

interface QuickActionsProps {
  onQuickAction: (actionText: string) => void;
  onOpenModal: (modalName: string) => void;
  onTriggerFileUpload: () => void;
}

export function QuickActions({ onQuickAction, onOpenModal, onTriggerFileUpload }: QuickActionsProps) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 w-full max-w-2xl pt-4">
      <button 
        type="button"
        onClick={() => onQuickAction("I have acute tooth pain. What should I check for and do?")}
        className="flex flex-col items-center gap-2 p-4 bg-dental-card border border-dental-border rounded-xl hover:bg-dental-border hover:border-dental-accent/50 transition-all group text-white text-center"
      >
        <Activity className="text-rose-400 w-6 h-6 group-hover:scale-110 transition-transform" />
        <span className="text-sm font-medium">Tooth Pain Help</span>
      </button>

      <button 
        type="button"
        onClick={() => onOpenModal("appointments")}
        className="flex flex-col items-center gap-2 p-4 bg-dental-card border border-dental-border rounded-xl hover:bg-dental-border hover:border-dental-accent/50 transition-all group text-white text-center"
      >
        <CalendarPlus className="text-sky-400 w-6 h-6 group-hover:scale-110 transition-transform" />
        <span className="text-sm font-medium">Book Appointment</span>
      </button>

      <button 
        type="button"
        onClick={onTriggerFileUpload}
        className="flex flex-col items-center gap-2 p-4 bg-dental-card border border-dental-border rounded-xl hover:bg-dental-border hover:border-dental-accent/50 transition-all group text-white text-center"
      >
        <UploadCloud className="text-purple-400 w-6 h-6 group-hover:scale-110 transition-transform" />
        <span className="text-sm font-medium">Upload X-ray</span>
      </button>

      <button 
        type="button"
        onClick={() => onOpenModal("tips")}
        className="flex flex-col items-center gap-2 p-4 bg-dental-card border border-dental-border rounded-xl hover:bg-dental-border hover:border-dental-accent/50 transition-all group text-white text-center"
      >
        <Sparkles className="text-amber-400 w-6 h-6 group-hover:scale-110 transition-transform" />
        <span className="text-sm font-medium">Dental Care Tips</span>
      </button>
    </div>
  );
}
