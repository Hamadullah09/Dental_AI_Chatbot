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
          className="absolute top-4 right-4 p-1.5 text-gray-400 hover:text-white hover:bg-white/5 rounded-lg transition-colors z-10"
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
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
        <input 
          type="text" 
          placeholder="Search articles..." 
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full bg-dental-darkBg border border-dental-border rounded-lg py-2 pl-9 pr-3 text-sm text-white focus:outline-none focus:border-dental-accent transition-colors"
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
                  : "text-gray-400 hover:text-white hover:bg-dental-card"
              }`}
            >
              <span className="block opacity-65 text-[10px] uppercase font-bold tracking-wider mb-0.5">{topic.category}</span>
              <span className="truncate block">{topic.title}</span>
            </button>
          )) : (
            <p className="text-xs text-gray-500 italic p-2">No articles found.</p>
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
                      <li key={index} className="flex gap-2 text-xs text-gray-300 leading-relaxed items-start">
                        <Check size={12} className="text-dental-accent mt-0.5 shrink-0" />
                        <span>{tip}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            );
          })() : (
            <div className="h-full flex items-center justify-center text-xs text-gray-500 italic">
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
            <label className="text-[10px] text-gray-400">Specialist Dentist</label>
            <div className="w-full bg-dental-darkBg border border-dental-border p-2 rounded-lg text-xs font-semibold text-white">
              Dr. Arthur Smith, DDS (Periodontics)
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-[10px] text-gray-400">Treatment Concern</label>
            <select 
              value={selectedTreatment} 
              onChange={(e) => setSelectedTreatment(e.target.value)}
              className="w-full bg-dental-darkBg border border-dental-border p-2 rounded-lg text-xs text-white focus:outline-none focus:border-dental-accent"
            >
              {treatments.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <label className="text-[10px] text-gray-400">Date</label>
              <input 
                type="date"
                required
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                min={new Date().toISOString().split("T")[0]}
                className="w-full bg-dental-darkBg border border-dental-border p-2 rounded-lg text-xs text-white focus:outline-none focus:border-dental-accent"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-gray-400">Time</label>
              <select 
                required
                value={selectedTime}
                onChange={(e) => setSelectedTime(e.target.value)}
                className="w-full bg-dental-darkBg border border-dental-border p-2 rounded-lg text-xs text-white focus:outline-none focus:border-dental-accent"
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
                className="p-2.5 bg-dental-darkBg border border-dental-border rounded-xl text-xs space-y-1 flex justify-between items-start"
              >
                <div>
                  <p className="font-semibold text-white">{appt.treatment}</p>
                  <p className="text-[10px] text-gray-400">{appt.doctor}</p>
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
              <p className="text-xs text-gray-600 italic mt-6 text-center">No scheduled appointments found.</p>
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
        { id: "1", name: "Dental_Panoramic_Xray_2025.png", type: "image/png", size: "1280 KB", date: "2026-05-12" },
        { id: "2", name: "Orthodontics_Treatment_Plan.pdf", type: "application/pdf", size: "340 KB", date: "2026-06-02" }
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
          <h2 className="text-xl font-bold">Patient Clinical Library</h2>
          <p className="text-xs text-dental-textSecondary">Upload and organize your dental X-rays, diagnostics, and prescriptions.</p>
        </div>
      </div>

      <div className="space-y-4">
        {/* Upload Container */}
        <div className="p-5 border-2 border-dashed border-dental-border hover:border-dental-accent/40 rounded-xl bg-dental-darkBg/60 text-center transition-all cursor-pointer relative">
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
              <ImageIcon className="mx-auto text-purple-400 w-8 h-8 mb-1" />
              <p className="text-xs font-semibold text-white">Drag & drop or click to upload</p>
              <p className="text-[10px] text-gray-500">Supports PNG, JPG, or PDF (X-rays, dental reports, prescriptions)</p>
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
                className="p-3 bg-dental-darkBg border border-dental-border rounded-xl text-xs flex justify-between items-center"
              >
                <div className="flex items-center gap-3 min-w-0">
                  {report.type.startsWith("image/") ? (
                    <ImageIcon className="text-purple-400 shrink-0" size={16} />
                  ) : (
                    <FileText className="text-teal-400 shrink-0" size={16} />
                  )}
                  <div className="min-w-0">
                    <p className="font-semibold text-white truncate max-w-[240px] md:max-w-[320px]">{report.name}</p>
                    <p className="text-[10px] text-gray-500">{report.size} · Uploaded: {report.date}</p>
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
              <p className="text-xs text-gray-600 italic text-center mt-6">No patient files uploaded yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* 4. DENTAL TIPS CAROUSEL CONTENT */
function TipsContent() {
  const [tipIndex, setTipIndex] = useState(0);

  const tips = [
    {
      title: "The 2-Minute Rule",
      desc: "Brushing for at least two minutes, twice a day, ensures you clear plaque from all surfaces. Many people brush for under 45 seconds. Keep a timer or use an electric toothbrush with automated timers.",
      stat: "Cuts cavity risks by up to 26%"
    },
    {
      title: "Don't Forget the Tongue",
      desc: "Plaque accumulates on your tongue's tiny papillae. This causes chronic bad breath (halitosis) and can transfer decay-inducing bacteria back to your teeth. Scrape or brush your tongue gently daily.",
      stat: "Reduces bad breath compounds by 75%"
    },
    {
      title: "Flossing Reaches 40% of Teeth",
      desc: "Toothbrush bristles cannot reach the tight contact areas between your teeth. If you do not floss, you leave nearly 40% of your tooth surfaces uncleaned, promoting plaque growth and proximal cavities.",
      stat: "Cleans spaces where most cavities form"
    },
    {
      title: "Enamel Erosion & Acidic Foods",
      desc: "Sugary treats and acidic juices soften your tooth enamel. Brushing immediately after eating these can actually scratch the weakened enamel. Rinse with water first, and wait 30 minutes before brushing.",
      stat: "Protects protective tooth structures"
    }
  ];

  const handleNext = () => {
    setTipIndex((prev) => (prev + 1) % tips.length);
  };

  const handlePrev = () => {
    setTipIndex((prev) => (prev - 1 + tips.length) % tips.length);
  };

  return (
    <div className="p-6">
      <div className="flex items-center gap-2 mb-4">
        <div className="bg-amber-500/10 p-2 rounded-lg text-amber-400">
          <Sparkles size={20} />
        </div>
        <div>
          <h2 className="text-xl font-bold">Dental Care Tips</h2>
          <p className="text-xs text-dental-textSecondary">Oral hygiene insights for a healthy, vibrant smile.</p>
        </div>
      </div>

      <div className="relative min-h-[180px] bg-dental-darkBg/60 border border-dental-border p-5 rounded-2xl flex flex-col justify-between items-center text-center">
        {/* Carousel slide details */}
        <div className="space-y-3 max-w-md my-auto">
          <span className="inline-block px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 text-[10px] font-bold">
            Insight {tipIndex + 1} of {tips.length}
          </span>
          <h3 className="text-base font-bold text-white leading-snug">{tips[tipIndex].title}</h3>
          <p className="text-xs text-dental-textSecondary leading-relaxed">{tips[tipIndex].desc}</p>
          <p className="text-[10px] text-dental-accent font-semibold">{tips[tipIndex].stat}</p>
        </div>

        {/* Carousel controls */}
        <div className="flex justify-between w-full absolute top-1/2 -translate-y-1/2 left-0 right-0 px-2 pointer-events-none">
          <button 
            onClick={handlePrev}
            className="p-1 rounded-full bg-dental-card border border-dental-border hover:bg-dental-border transition-colors text-white pointer-events-auto shrink-0"
          >
            <ChevronLeft size={16} />
          </button>
          <button 
            onClick={handleNext}
            className="p-1 rounded-full bg-dental-card border border-dental-border hover:bg-dental-border transition-colors text-white pointer-events-auto shrink-0"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
      
      {/* Slider dots indicators */}
      <div className="flex justify-center gap-1.5 mt-4">
        {tips.map((_, i) => (
          <button 
            key={i} 
            onClick={() => setTipIndex(i)}
            className={`w-2 h-2 rounded-full transition-all ${i === tipIndex ? "bg-dental-accent w-4" : "bg-dental-border"}`}
          />
        ))}
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
  const [modelType, setModelType] = useState("gpt-4o-mini");
  const [temperature, setTemperature] = useState(0.3);
  const [topK, setTopK] = useState(5);
  const [savedSettings, setSavedSettings] = useState(false);

  const handleSave = () => {
    setSavedSettings(true);
    setTimeout(() => setSavedSettings(false), 2000);
  };

  const handleResetChatMemory = () => {
    localStorage.removeItem("dental_ai_appointments");
    localStorage.removeItem("dental_ai_reports");
    alert("Chat cache and mock data reset successfully!");
  };

  return (
    <div className="p-6">
      <div className="flex items-center gap-2 mb-4">
        <div className="bg-gray-500/10 p-2 rounded-lg text-gray-400">
          <Settings size={20} />
        </div>
        <div>
          <h2 className="text-xl font-bold">Preferences & Settings</h2>
          <p className="text-xs text-dental-textSecondary">Configure workspace behavior and mock RAG properties.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 h-[320px]">
        {/* Left Side: General Profile */}
        <div className="space-y-4 border-r border-dental-border/50 pr-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-dental-accent">Account details</h3>
          
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-dental-accent to-blue-600 flex items-center justify-center font-bold text-sm shrink-0">
                {user?.full_name ? user.full_name.substring(0, 2).toUpperCase() : "JD"}
              </div>
              <div className="min-w-0">
                <p className="text-xs text-gray-400">Logged in as</p>
                <p className="text-sm font-bold truncate text-white">{user?.full_name || "Wazeer Ali"}</p>
                <p className="text-[10px] text-dental-textSecondary truncate">{user?.email || "patient@example.com"}</p>
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-[10px] text-gray-400 block">Workspace Theme</label>
              <button 
                onClick={toggleTheme}
                className="w-full flex justify-between items-center px-3 py-2 bg-dental-darkBg border border-dental-border rounded-lg text-xs font-semibold text-white"
              >
                <span className="flex items-center gap-2">
                  {theme === "dark" ? <Moon size={14} className="text-yellow-400" /> : <Sun size={14} />}
                  Theme Mode: {theme === "dark" ? "Dark default" : "Light theme"}
                </span>
                <span className="text-[10px] text-dental-accent uppercase font-bold">Toggle</span>
              </button>
            </div>

            <div className="pt-2">
              <button 
                onClick={handleResetChatMemory}
                className="w-full py-2 bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 rounded-lg text-[10px] font-bold transition-all"
              >
                Clear Simulated Local Cache
              </button>
            </div>
          </div>
        </div>

        {/* Right Side: RAG / LLM tuning */}
        <div className="space-y-4 overflow-y-auto">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-sky-400">RAG configurations</h3>
          
          <div className="space-y-3 text-xs">
            <div className="space-y-1">
              <label className="text-[10px] text-gray-400 block">RAG Retrieval Top-K Chunks ({topK})</label>
              <input 
                type="range"
                min="1"
                max="12"
                value={topK}
                onChange={(e) => setTopK(parseInt(e.target.value))}
                className="w-full h-1 bg-dental-border rounded-lg appearance-none cursor-pointer accent-dental-accent"
              />
              <span className="text-[10px] text-gray-500 block">Number of sources to retrieve from vector database.</span>
            </div>

            <div className="space-y-1">
              <label className="text-[10px] text-gray-400 block">LLM Processing Model</label>
              <select 
                value={modelType}
                onChange={(e) => setModelType(e.target.value)}
                className="w-full bg-dental-darkBg border border-dental-border p-2 rounded-lg text-xs text-white focus:outline-none focus:border-dental-accent"
              >
                <option value="gpt-4o-mini">gpt-4o-mini (Faster - Recommended)</option>
                <option value="gpt-4o">gpt-4o (Higher factuality)</option>
                <option value="extractive">Local Extractive Fallback (No internet)</option>
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-[10px] text-gray-400 block">LLM Temperature ({temperature})</label>
              <input 
                type="range"
                min="0.0"
                max="1.0"
                step="0.1"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-full h-1 bg-dental-border rounded-lg appearance-none cursor-pointer accent-dental-accent"
              />
              <span className="text-[10px] text-gray-500 block">Lower value makes responses more strict and analytical.</span>
            </div>

            <button 
              onClick={handleSave}
              className="w-full py-2 bg-dental-accent hover:bg-dental-accentHover text-white rounded-lg font-bold transition-all"
            >
              {savedSettings ? "Saved Configuration!" : "Save RAG Parameters"}
            </button>
          </div>
        </div>
      </div>
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
      description: "Advanced diagnostic support, image-based X-ray assistance, and clinic exports.",
      features: [
        "Unlimited messages daily",
        "X-ray upload diagnostic analysis",
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
          <p className="text-xs text-dental-textSecondary">Unlock diagnostic capabilities and advanced X-ray processing filters.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {tiers.map((tier) => (
          <div 
            key={tier.name}
            className={`p-4 rounded-xl border flex flex-col justify-between relative transition-all ${
              tier.popular 
                ? "bg-dental-card border-dental-accent/60 shadow-lg shadow-dental-accent/5" 
                : "bg-dental-darkBg border-dental-border hover:border-dental-border/80"
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
                {tier.period && <span className="text-[10px] text-gray-500">{tier.period}</span>}
              </div>
              <p className="text-[10px] text-dental-textSecondary leading-normal min-h-[36px]">{tier.description}</p>
              
              <div className="border-t border-dental-border/40 pt-2 my-2">
                <ul className="space-y-1">
                  {tier.features.map((feat) => (
                    <li key={feat} className="flex gap-1 text-[9px] text-gray-300 leading-relaxed items-start">
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
                    : "bg-dental-border hover:bg-white/5 text-gray-300"
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
          <p className="text-xs text-dental-textSecondary">Tailor the chatbot's vocabulary and diagnostic expertise focus.</p>
        </div>
      </div>

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <label className="text-[10px] text-gray-400 block">Personal Profile Context</label>
            <select 
              value={dentalRole} 
              onChange={(e) => setDentalRole(e.target.value)}
              className="w-full bg-dental-darkBg border border-dental-border p-2 rounded-lg text-xs text-white focus:outline-none"
            >
              <option value="patient">Standard Patient (Layman definitions)</option>
              <option value="student">Dental Student (Clinical references)</option>
              <option value="dentist">Professional Dentist (Advanced pathology terms)</option>
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-[10px] text-gray-400 block">Specialty Retrieval Priority</label>
            <select 
              value={specialtyFocus} 
              onChange={(e) => setSpecialtyFocus(e.target.value)}
              className="w-full bg-dental-darkBg border border-dental-border p-2 rounded-lg text-xs text-white focus:outline-none"
            >
              <option value="general">General Oral Health & Cleanliness</option>
              <option value="surgery">Oral & Maxillofacial Surgery</option>
              <option value="orthodontics">Orthodontics & Braces alignment</option>
              <option value="periodontics">Periodontology (Gums and support)</option>
            </select>
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-[10px] text-gray-400 block">AI Speech Tone & Response Level</label>
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
                    : "bg-dental-darkBg border-dental-border text-gray-400 hover:text-white"
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
