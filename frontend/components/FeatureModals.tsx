"use client";

import React, { useState, useEffect } from "react";
import { 
  X, Calendar, Clock, Heart, Plus, Search, 
  FileText, ImageIcon, Check, Sparkles, Moon, Sun, 
  User, ShieldAlert, BadgeInfo, Stethoscope, ChevronLeft, ChevronRight,
  Settings
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeModal: string;
  onSelectSession?: (id: string) => void;
  onSendAttachedMessage?: (filename: string, content: string) => void;
}

export function FeatureModals({ 
  isOpen, 
  onClose, 
  activeModal,
  onSendAttachedMessage 
}: ModalProps) {
  const { user } = useAuth();
  const { theme, toggleTheme } = useTheme();
  
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-2xl bg-dental-card border border-dental-border rounded-2xl shadow-2xl overflow-hidden text-white animate-in zoom-in-95 duration-200">
        
        {/* Close Button */}
        <button 
          onClick={onClose}
          className="absolute top-4 right-4 p-1.5 text-dental-textMuted hover:text-dental-textPrimary hover:bg-dental-muted rounded-lg transition-colors z-10"
        >
          <X size={18} />
        </button>

        {/* Render Active Modal Content */}
        {activeModal === "library" && <LibraryContent />}
        {activeModal === "appointments" && <AppointmentsContent />}
        {activeModal === "reports" && <ReportsContent onSendAttachedMessage={onSendAttachedMessage} onClose={onClose} />}
        {activeModal === "tips" && <TipsContent />}
        {activeModal === "settings" && <SettingsContent theme={theme} toggleTheme={toggleTheme} />}
        {activeModal === "upgrade" && <UpgradeContent />}
        {activeModal === "personalization" && <PersonalizationContent />}
      </div>
    </div>
  );
}

/* 1. PATIENT LIBRARY CONTENT */
function LibraryContent() {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTopic, setActiveTopic] = useState<number | null>(0);

  const topics = [
    {
      id: 0,
      title: "Cavities & Tooth Decay",
      category: "Prevention",
      summary: "Understanding dental caries, how plaque acids dissolve enamel, and the role of fluoride in remineralization.",
      tips: [
        "Brush twice daily with a fluoride toothpaste containing 1000-1450ppm fluoride.",
        "Floss once daily to clean between teeth where bristles cannot reach.",
        "Limit snacking on sugary or acidic foods throughout the day to reduce acid attacks."
      ]
    },
    {
      id: 1,
      title: "Gingivitis & Gum Health",
      category: "Periodontal Care",
      summary: "Gingivitis is the early stage of gum disease characterized by red, swollen, or bleeding gums. It is completely reversible with good hygiene.",
      tips: [
        "Regular dental cleanings every 6 months are crucial to remove hardened tartar.",
        "Use an antiseptic or fluoride mouthwash to help reduce plaque bacteria.",
        "Watch for bleeding during brushing; it is a sign you need to clean *better*, not stop cleaning."
      ]
    },
    {
      id: 2,
      title: "Teeth Whitening Safety",
      category: "Restorative",
      summary: "Teeth whitening uses peroxide agents to bleach surface stains. While effective, it must be monitored to prevent tooth sensitivity and gum irritation.",
      tips: [
        "Consult your dentist before bleaching; whitening does not affect crowns, fillings, or veneers.",
        "If sensitivity occurs, use a potassium nitrate desensitizing toothpaste.",
        "Avoid staining foods (coffee, tea, red wine, soy sauce) for 48 hours after a whitening treatment."
      ]
    },
    {
      id: 3,
      title: "Wisdom Teeth Care",
      category: "Oral Surgery",
      summary: "Wisdom teeth (third molars) often become impacted due to lack of space, causing infection, alignment issues, or cyst formation.",
      tips: [
        "Keep the extraction site clean by rinsing with warm saltwater 24 hours post-surgery.",
        "Avoid using straws, smoking, or spitting for 48 hours to prevent dislodging the blood clot (dry socket).",
        "Eat soft foods like yogurt, mashed potatoes, or smoothies, and avoid hot liquids initially."
      ]
    }
  ];

  const filteredTopics = topics.filter(topic => 
    topic.title.toLowerCase().includes(searchQuery.toLowerCase()) || 
    topic.summary.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="p-6">
      <div className="flex items-center gap-2 mb-4">
        <div className="bg-teal-500/10 p-2 rounded-lg text-teal-400">
          <Stethoscope size={20} />
        </div>
        <div>
          <h2 className="text-xl font-bold">Patient Library</h2>
          <p className="text-xs text-dental-textSecondary">Educational guidelines and symptom-care articles.</p>
        </div>
      </div>

      {/* Search Input */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dental-textMuted" />
        <input 
          type="text" 
          placeholder="Search articles..." 
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full bg-dental-input border border-dental-border rounded-lg py-2 pl-9 pr-3 text-sm text-dental-textPrimary placeholder:text-dental-textMuted focus:outline-none focus:border-dental-accent transition-colors"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-4 h-[320px]">
        {/* Left Side: Topic list */}
        <div className="md:col-span-2 overflow-y-auto space-y-1 pr-1 border-r border-dental-border/50">
          {filteredTopics.length ? filteredTopics.map((topic) => (
            <button
              key={topic.id}
              onClick={() => setActiveTopic(topic.id)}
              className={`w-full text-left p-2.5 rounded-lg text-xs font-semibold transition-colors block truncate ${
                activeTopic === topic.id
                  ? "bg-dental-accent text-white"
                  : "text-dental-textSecondary hover:text-dental-textPrimary hover:bg-dental-muted"
              }`}
            >
              <span className="block opacity-65 text-[10px] uppercase font-bold tracking-wider mb-0.5">{topic.category}</span>
              <span className="truncate block">{topic.title}</span>
            </button>
          )) : (
            <p className="text-xs text-dental-textMuted italic p-2">No articles found.</p>
          )}
        </div>

        {/* Right Side: Details */}
        <div className="md:col-span-3 overflow-y-auto pl-1 pr-1">
          {activeTopic !== null ? (() => {
            const topic = topics.find(t => t.id === activeTopic);
            if (!topic) return null;
            return (
              <div className="space-y-4 fade-in">
                <div>
                  <span className="inline-block px-2 py-0.5 rounded-full bg-dental-accent/15 text-dental-accent text-[9px] font-bold uppercase tracking-wider mb-1">
                    {topic.category}
                  </span>
                  <h3 className="text-base font-bold text-white">{topic.title}</h3>
                </div>
                <p className="text-xs text-dental-textSecondary leading-relaxed">{topic.summary}</p>
                <div className="space-y-2">
                  <h4 className="text-[11px] font-semibold text-white/90 uppercase tracking-wide">Key Care Advice:</h4>
                  <ul className="space-y-1.5">
                    {topic.tips.map((tip, index) => (
                      <li key={index} className="flex gap-2 text-xs text-dental-textSecondary leading-relaxed items-start">
                        <Check size={12} className="text-dental-accent mt-0.5 shrink-0" />
                        <span>{tip}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            );
          })() : (
            <div className="h-full flex items-center justify-center text-xs text-dental-textMuted italic">
              Select an article to read.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* 2. APPOINTMENTS CONTENT */
function AppointmentsContent() {
  const [appointments, setAppointments] = useState<any[]>([]);
  const [selectedDate, setSelectedDate] = useState("");
  const [selectedTime, setSelectedTime] = useState("");
  const [selectedTreatment, setSelectedTreatment] = useState("Routine Cleaning");
  const [successMsg, setSuccessMsg] = useState("");

  const treatments = [
    "Routine Cleaning",
    "Dental Filling",
    "Wisdom Tooth Consultation",
    "Teeth Whitening",
    "Emergency Consultation"
  ];

  const timeSlots = ["09:00 AM", "10:30 AM", "01:00 PM", "02:30 PM", "04:00 PM"];

  useEffect(() => {
    const stored = localStorage.getItem("dental_ai_appointments");
    if (stored) {
      setAppointments(JSON.parse(stored));
    } else {
      const dummy = [
        { id: "1", doctor: "Dr. Arthur Smith (DDS)", treatment: "Routine Cleaning", date: "2026-06-25", time: "10:30 AM" }
      ];
      setAppointments(dummy);
      localStorage.setItem("dental_ai_appointments", JSON.stringify(dummy));
    }
  }, []);

  const handleBook = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDate || !selectedTime) return;

    const newBooking = {
      id: crypto.randomUUID(),
      doctor: "Dr. Arthur Smith (DDS)",
      treatment: selectedTreatment,
      date: selectedDate,
      time: selectedTime
    };

    const nextBookings = [newBooking, ...appointments];
    setAppointments(nextBookings);
    localStorage.setItem("dental_ai_appointments", JSON.stringify(nextBookings));

    setSuccessMsg(`Appointment booked: ${selectedTreatment} with Dr. Smith on ${selectedDate} at ${selectedTime}!`);
    setSelectedDate("");
    setSelectedTime("");
    setTimeout(() => setSuccessMsg(""), 4000);
  };

  const handleDelete = (id: string) => {
    const nextBookings = appointments.filter(b => b.id !== id);
    setAppointments(nextBookings);
    localStorage.setItem("dental_ai_appointments", JSON.stringify(nextBookings));
  };

  return (
    <div className="p-6">
      <div className="flex items-center gap-2 mb-4">
        <div className="bg-sky-500/10 p-2 rounded-lg text-sky-400">
          <Calendar size={20} />
        </div>
        <div>
          <h2 className="text-xl font-bold">Dental Appointment Scheduler</h2>
          <p className="text-xs text-dental-textSecondary">Schedule or manage your consultations with our specialist.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Book Form */}
        <form onSubmit={handleBook} className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-dental-accent">Schedule Slot</h3>
          
          <div className="space-y-1">
            <label className="text-[10px] text-dental-textSecondary">Specialist Dentist</label>
            <div className="w-full bg-dental-input border border-dental-border p-2 rounded-lg text-xs font-semibold text-dental-textPrimary">
              Dr. Arthur Smith, DDS (Periodontics)
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-[10px] text-dental-textSecondary">Treatment Concern</label>
            <select 
              value={selectedTreatment} 
              onChange={(e) => setSelectedTreatment(e.target.value)}
              className="w-full bg-dental-input border border-dental-border p-2 rounded-lg text-xs text-dental-textPrimary placeholder:text-dental-textMuted focus:outline-none focus:border-dental-accent"
            >
              {treatments.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <label className="text-[10px] text-dental-textSecondary">Date</label>
              <input 
                type="date"
                required
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                min={new Date().toISOString().split("T")[0]}
                className="w-full bg-dental-input border border-dental-border p-2 rounded-lg text-xs text-dental-textPrimary focus:outline-none focus:border-dental-accent"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-dental-textSecondary">Time</label>
              <select 
                required
                value={selectedTime}
                onChange={(e) => setSelectedTime(e.target.value)}
                className="w-full bg-dental-input border border-dental-border p-2 rounded-lg text-xs text-dental-textPrimary focus:outline-none focus:border-dental-accent"
              >
                <option value="">Select slot</option>
                {timeSlots.map((ts) => (
                  <option key={ts} value={ts}>{ts}</option>
                ))}
              </select>
            </div>
          </div>

          <button 
            type="submit"
            className="w-full py-2 bg-dental-accent hover:bg-dental-accentHover text-white rounded-lg text-xs font-bold transition-all shadow-md mt-4"
          >
            Confirm Appointment Slot
          </button>

          {successMsg && (
            <p className="text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 p-2 rounded-lg text-center animate-in fade-in">
              {successMsg}
            </p>
          )}
        </form>

        {/* Bookings List */}
        <div className="flex flex-col h-[280px]">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-sky-400 mb-2">My Appointments</h3>
          <div className="flex-1 overflow-y-auto space-y-2 pr-1">
            {appointments.length ? appointments.map((appt) => (
              <div 
                key={appt.id}
                className="p-2.5 bg-dental-elevated border border-dental-border rounded-xl text-xs space-y-1 flex justify-between items-start"
              >
                <div>
                  <p className="font-semibold text-white">{appt.treatment}</p>
                  <p className="text-[10px] text-dental-textSecondary">{appt.doctor}</p>
                  <div className="flex items-center gap-3 text-[10px] text-dental-accent font-medium mt-1">
                    <span className="flex items-center gap-1"><Calendar size={10} />{appt.date}</span>
                    <span className="flex items-center gap-1"><Clock size={10} />{appt.time}</span>
                  </div>
                </div>
                <button 
                  onClick={() => handleDelete(appt.id)}
                  className="text-red-400 hover:text-red-300 text-[10px] hover:underline"
                >
                  Cancel
                </button>
              </div>
            )) : (
              <p className="text-xs text-dental-textMuted italic mt-6 text-center">No scheduled appointments found.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* 3. REPORTS CONTENT */
interface ReportsContentProps {
  onClose: () => void;
  onSendAttachedMessage?: (filename: string, content: string) => void;
}

function ReportsContent({ onClose, onSendAttachedMessage }: ReportsContentProps) {
  const [reports, setReports] = useState<any[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  useEffect(() => {
    const stored = localStorage.getItem("dental_ai_reports");
    if (stored) {
      setReports(JSON.parse(stored));
    } else {
      const dummy = [
        { id: "1", name: "Orthodontics_Treatment_Plan.pdf", type: "application/pdf", size: "340 KB", date: "2026-06-02" },
        { id: "2", name: "Patient_Education_Notes.pdf", type: "application/pdf", size: "228 KB", date: "2026-06-08" }
      ];
      setReports(dummy);
      localStorage.setItem("dental_ai_reports", JSON.stringify(dummy));
    }
  }, []);

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setIsUploading(true);
      setUploadProgress(10);
      
      const interval = setInterval(() => {
        setUploadProgress(prev => {
          if (prev >= 100) {
            clearInterval(interval);
            setTimeout(() => {
              const newReport = {
                id: crypto.randomUUID(),
                name: file.name,
                type: file.type,
                size: `${(file.size / 1024).toFixed(0)} KB`,
                date: new Date().toISOString().split("T")[0]
              };
              const nextReports = [newReport, ...reports];
              setReports(nextReports);
              localStorage.setItem("dental_ai_reports", JSON.stringify(nextReports));
              setIsUploading(false);
            }, 500);
            return 100;
          }
          return prev + 30;
        });
      }, 200);
    }
  };

  const handleDelete = (id: string) => {
    const nextReports = reports.filter(r => r.id !== id);
    setReports(nextReports);
    localStorage.setItem("dental_ai_reports", JSON.stringify(nextReports));
  };

  const handleAnalyzeInChat = (report: any) => {
    if (onSendAttachedMessage) {
      onSendAttachedMessage(
        report.name,
        `I've attached my report **${report.name}**. Please analyze its content and summarize key dental observations.`
      );
      onClose();
    }
  };

  return (
    <div className="p-6">
      <div className="flex items-center gap-2 mb-4">
        <div className="bg-purple-500/10 p-2 rounded-lg text-purple-400">
          <FileText size={20} />
        </div>
        <div>
          <h2 className="text-xl font-bold">Patient Files</h2>
          <p className="text-xs text-dental-textSecondary">Upload and organize dental PDFs, reports, prescriptions, and reference documents.</p>
        </div>
      </div>

      <div className="space-y-4">
        {/* Upload Container */}
        <div className="p-5 border-2 border-dashed border-dental-border hover:border-dental-accent/40 rounded-xl bg-dental-elevated text-center transition-all cursor-pointer relative">
          <input 
            type="file" 
            className="absolute inset-0 opacity-0 cursor-pointer"
            onChange={handleUpload}
            disabled={isUploading}
          />
          {isUploading ? (
            <div className="space-y-2 py-2">
              <p className="text-xs text-white">Uploading clinical file: {uploadProgress}%</p>
              <div className="w-full bg-dental-border h-1.5 rounded-full overflow-hidden max-w-xs mx-auto">
                <div 
                  className="bg-dental-accent h-full transition-all duration-150"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          ) : (
            <div className="space-y-1">
              <FileText className="mx-auto text-purple-400 w-8 h-8 mb-1" />
              <p className="text-xs font-semibold text-white">Drag & drop or click to upload</p>
              <p className="text-[10px] text-dental-textMuted">Supports PDF documents for dental reports, prescriptions, and study references</p>
            </div>
          )}
        </div>

        {/* Document list */}
        <div className="flex flex-col h-[200px]">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-purple-400 mb-2">My Uploaded Files</h3>
          <div className="flex-1 overflow-y-auto space-y-2 pr-1">
            {reports.length ? reports.map((report) => (
              <div 
                key={report.id}
                className="p-3 bg-dental-elevated border border-dental-border rounded-xl text-xs flex justify-between items-center"
              >
                <div className="flex items-center gap-3 min-w-0">
                  {report.type.startsWith("image/") ? (
                    <ImageIcon className="text-purple-400 shrink-0" size={16} />
                  ) : (
                    <FileText className="text-teal-400 shrink-0" size={16} />
                  )}
                  <div className="min-w-0">
                    <p className="font-semibold text-white truncate max-w-[240px] md:max-w-[320px]">{report.name}</p>
                    <p className="text-[10px] text-dental-textMuted">{report.size} · Uploaded: {report.date}</p>
                  </div>
                </div>
                
                <div className="flex items-center gap-3 shrink-0">
                  <button 
                    onClick={() => handleAnalyzeInChat(report)}
                    className="text-[10px] text-dental-accent hover:underline font-bold"
                  >
                    Analyze in Chat
                  </button>
                  <button 
                    onClick={() => handleDelete(report.id)}
                    className="text-red-400 hover:text-red-300 text-[10px] hover:underline"
                  >
                    Delete
                  </button>
                </div>
              </div>
            )) : (
              <p className="text-xs text-dental-textMuted italic text-center mt-6">No patient files uploaded yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* 4. HELP CONTENT */
function TipsContent() {
  const helpItems = [
    {
      title: "Ask grounded questions",
      description: "Use clear dental questions. DentalGPT will answer from uploaded PDFs when matching evidence is available.",
    },
    {
      title: "Use web search intentionally",
      description: "Enable web search only when you need current information from trusted online sources.",
    },
    {
      title: "Upload clinical documents",
      description: "Attach PDF references or reports when you want answers scoped to a specific document.",
    },
    {
      title: "Medical safety",
      description: "DentalGPT is for education and decision support. For diagnosis, treatment, or emergencies, consult a licensed dentist.",
    },
  ];

  return (
    <div className="p-6 text-white">
      <div className="mb-6">
        <h2 className="text-2xl font-semibold">Help</h2>
        <p className="mt-1 text-sm text-white/55">Quick guidance for using DentalGPT safely and effectively.</p>
      </div>

      <div className="space-y-2">
        {helpItems.map((item) => (
          <div key={item.title} className="rounded-2xl border border-dental-border bg-dental-elevated p-4">
            <p className="font-medium">{item.title}</p>
            <p className="mt-1 text-sm leading-6 text-white/60">{item.description}</p>
          </div>
        ))}
      </div>

      <div className="mt-5 rounded-2xl border border-amber-400/20 bg-amber-400/10 p-4 text-sm text-amber-100">
        If symptoms are severe, worsening, or urgent, contact a dentist or emergency service instead of relying on the chatbot.
      </div>
    </div>
  );
}

/* 5. SETTINGS CONTENT */
interface SettingsProps {
  theme: string;
  toggleTheme: () => void;
}

function SettingsContent({ theme, toggleTheme }: SettingsProps) {
  const { user } = useAuth();
  const initials = user?.full_name
    ? user.full_name.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase()
    : user?.email?.slice(0, 2).toUpperCase() || "DA";

  return (
    <div className="grid h-[520px] grid-cols-1 bg-dental-card text-dental-textPrimary md:grid-cols-[220px_1fr]">
      <aside className="border-b border-dental-border p-3 md:border-b-0 md:border-r">
        <button className="flex w-full items-center gap-3 rounded-xl bg-white/10 px-3 py-3 text-left text-sm font-semibold">
          <Settings size={18} />
          General
        </button>
        <button className="mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm text-white/75 hover:bg-white/10">
          <ShieldAlert size={18} />
          Safety
        </button>
        <button className="mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm text-white/75 hover:bg-white/10">
          <BadgeInfo size={18} />
          About
        </button>
      </aside>

      <section className="overflow-y-auto p-6">
        <h2 className="text-2xl font-semibold">General</h2>
        <div className="mt-6 divide-y divide-white/10">
          <div className="flex items-center justify-between gap-4 py-5">
            <div>
              <p className="font-medium">Account</p>
              <p className="mt-1 text-sm text-white/55">{user?.email || "Signed in user"}</p>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-orange-600 text-sm font-bold">
              {initials}
            </div>
          </div>

          <div className="flex items-center justify-between gap-4 py-5">
            <div>
              <p className="font-medium">Appearance</p>
              <p className="mt-1 text-sm text-white/55">Switch between dark and light workspace mode.</p>
            </div>
            <button
              type="button"
              onClick={toggleTheme}
              className="inline-flex min-w-[116px] items-center justify-center gap-2 rounded-xl border border-dental-border px-3 py-2 text-sm text-dental-textPrimary hover:bg-dental-muted"
            >
              {theme === "dark" ? <Moon size={16} /> : <Sun size={16} />}
              {theme === "dark" ? "Dark" : "Light"}
            </button>
          </div>

          <div className="flex items-center justify-between gap-4 py-5">
            <div>
              <p className="font-medium">Grounded answers</p>
              <p className="mt-1 text-sm text-white/55">DentalGPT answers from uploaded clinical references when evidence is available.</p>
            </div>
            <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-semibold text-emerald-300">Enabled</span>
          </div>

          <div className="flex items-center justify-between gap-4 py-5">
            <div>
              <p className="font-medium">Medical safety notice</p>
              <p className="mt-1 text-sm text-white/55">DentalGPT is educational and does not replace a licensed dentist.</p>
            </div>
            <span className="rounded-full bg-white/10 px-3 py-1 text-xs text-white/70">Always shown</span>
          </div>
        </div>
      </section>
    </div>
  );
}

/* 6. UPGRADE PLAN CONTENT */
function UpgradeContent() {
  const [tierSelected, setTierSelected] = useState<string | null>(null);

  const tiers = [
    {
      name: "Free Basic",
      price: "$0",
      description: "Fundamental AI chat grounded in general public dental facts.",
      features: [
        "Up to 15 messages per day",
        "Public dental education access",
        "Standard RAG context extraction"
      ]
    },
    {
      name: "Patient Pro",
      price: "$19",
      period: "/month",
      popular: true,
      description: "Advanced dental document support, clinical exports, and guided patient education.",
      features: [
        "Unlimited messages daily",
        "PDF upload and document-grounded chat",
        "Dr. Smith consultation booking sync",
        "HIPAA-compliant document exports"
      ]
    },
    {
      name: "Clinic Expert",
      price: "$49",
      period: "/month",
      description: "Multi-tenant medical support, student study plans, and custom vector bases.",
      features: [
        "Shared staff workspaces",
        "Integrates with dental CRM databases",
        "Upload custom clinical textbook libraries",
        "Patient symptom charts telemetry"
      ]
    }
  ];

  return (
    <div className="p-6">
      <div className="flex items-center gap-2 mb-4">
        <div className="bg-teal-500/10 p-2 rounded-lg text-teal-400">
          <Sparkles size={20} />
        </div>
        <div>
          <h2 className="text-xl font-bold">Upgrade Membership Plan</h2>
          <p className="text-xs text-dental-textSecondary">Unlock advanced document workflows and clinical review features.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {tiers.map((tier) => (
          <div 
            key={tier.name}
            className={`p-4 rounded-xl border flex flex-col justify-between relative transition-all ${
              tier.popular 
                ? "bg-dental-card border-dental-accent/60 shadow-lg shadow-dental-accent/5" 
                : "bg-dental-elevated border-dental-border hover:border-dental-borderStrong"
            }`}
          >
            {tier.popular && (
              <span className="absolute -top-2 left-1/2 -translate-x-1/2 px-2 py-0.5 rounded-full bg-dental-accent text-[8px] font-bold text-white uppercase tracking-wider">
                Most Popular
              </span>
            )}

            <div className="space-y-2 mb-4">
              <h3 className="text-xs font-bold text-white">{tier.name}</h3>
              <div className="flex items-baseline gap-0.5">
                <span className="text-2xl font-bold text-white">{tier.price}</span>
                {tier.period && <span className="text-[10px] text-dental-textMuted">{tier.period}</span>}
              </div>
              <p className="text-[10px] text-dental-textSecondary leading-normal min-h-[36px]">{tier.description}</p>
              
              <div className="border-t border-dental-border/40 pt-2 my-2">
                <ul className="space-y-1">
                  {tier.features.map((feat) => (
                    <li key={feat} className="flex gap-1 text-[9px] text-dental-textSecondary leading-relaxed items-start">
                      <Check size={10} className="text-dental-accent mt-0.5 shrink-0" />
                      <span className="truncate">{feat}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {tierSelected === tier.name ? (
              <div className="w-full py-1.5 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-emerald-400 font-bold text-[10px] text-center">
                Subscribed!
              </div>
            ) : (
              <button 
                onClick={() => setTierSelected(tier.name)}
                className={`w-full py-1.5 rounded-lg text-[10px] font-bold transition-all ${
                  tier.popular
                    ? "bg-dental-accent hover:bg-dental-accentHover text-white"
                    : "bg-dental-muted hover:bg-dental-border text-dental-textPrimary"
                }`}
              >
                {tier.price === "$0" ? "Current Tier" : `Choose ${tier.name.split(" ")[1]}`}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* 7. PERSONALIZATION CONTENT */
function PersonalizationContent() {
  const [dentalRole, setDentalRole] = useState("patient");
  const [specialtyFocus, setSpecialtyFocus] = useState("general");
  const [aiAssistantTone, setAiAssistantTone] = useState("calm");
  const [success, setSuccess] = useState(false);

  const handleSave = () => {
    setSuccess(true);
    setTimeout(() => setSuccess(false), 2000);
  };

  return (
    <div className="p-6">
      <div className="flex items-center gap-2 mb-4">
        <div className="bg-yellow-500/10 p-2 rounded-lg text-yellow-400">
          <Sparkles size={20} />
        </div>
        <div>
          <h2 className="text-xl font-bold">AI Assistant Personalization</h2>
          <p className="text-xs text-dental-textSecondary">Tailor the chatbot&apos;s vocabulary and diagnostic expertise focus.</p>
        </div>
      </div>

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <label className="text-[10px] text-dental-textSecondary block">Personal Profile Context</label>
            <select 
              value={dentalRole} 
              onChange={(e) => setDentalRole(e.target.value)}
              className="w-full bg-dental-input border border-dental-border p-2 rounded-lg text-xs text-dental-textPrimary focus:outline-none"
            >
              <option value="patient">Standard Patient (Layman definitions)</option>
              <option value="student">Dental Student (Clinical references)</option>
              <option value="dentist">Professional Dentist (Advanced pathology terms)</option>
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-[10px] text-dental-textSecondary block">Specialty Retrieval Priority</label>
            <select 
              value={specialtyFocus} 
              onChange={(e) => setSpecialtyFocus(e.target.value)}
              className="w-full bg-dental-input border border-dental-border p-2 rounded-lg text-xs text-dental-textPrimary focus:outline-none"
            >
              <option value="general">General Oral Health & Cleanliness</option>
              <option value="surgery">Oral & Maxillofacial Surgery</option>
              <option value="orthodontics">Orthodontics & Braces alignment</option>
              <option value="periodontics">Periodontology (Gums and support)</option>
            </select>
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-[10px] text-dental-textSecondary block">AI Speech Tone & Response Level</label>
          <div className="grid grid-cols-3 gap-2">
            {[
              { id: "calm", label: "Calm & Trustworthy", desc: "Reassuring medical support" },
              { id: "strict", label: "Clinical & Strict", desc: "Direct scientific findings" },
              { id: "instructive", label: "Step-by-Step Instructor", desc: "Actionable hygiene tasks" }
            ].map((tone) => (
              <button
                key={tone.id}
                type="button"
                onClick={() => setAiAssistantTone(tone.id)}
                className={`p-2.5 rounded-xl border text-left flex flex-col justify-between transition-all ${
                  aiAssistantTone === tone.id 
                    ? "bg-dental-accent/15 border-dental-accent text-white" 
                    : "bg-dental-elevated border-dental-border text-dental-textSecondary hover:text-dental-textPrimary"
                }`}
              >
                <span className="text-[10px] font-bold block">{tone.label}</span>
                <span className="text-[8px] opacity-75 mt-0.5">{tone.desc}</span>
              </button>
            ))}
          </div>
        </div>

        <button 
          onClick={handleSave}
          className="w-full py-2 bg-dental-accent hover:bg-dental-accentHover text-white rounded-lg text-xs font-bold transition-all shadow-md mt-2"
        >
          {success ? "Personalization settings applied!" : "Apply AI Preferences"}
        </button>
      </div>
    </div>
  );
}
