"use client";

import { useState, useEffect } from "react";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { useAuth } from "@/lib/auth";
import { useRouter, useSearchParams } from "next/navigation";
import {
  getAppointments,
  getUpcomingAppointments,
  getDentists,
  createAppointment,
  updateAppointmentStatus,
} from "@/lib/api";
import type { Appointment, Dentist } from "@/lib/types";
import {
  Calendar,
  Clock,
  Plus,
  X,
  Check,
  AlertCircle,
  ChevronRight,
} from "lucide-react";

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  confirmed: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  completed: "bg-green-500/10 text-green-400 border-green-500/20",
  cancelled: "bg-red-500/10 text-red-400 border-red-500/20",
  rejected: "bg-red-500/10 text-red-400 border-red-500/20",
  no_show: "bg-gray-500/10 text-gray-400 border-gray-500/20",
};

function AppointmentsContent() {
  const { token } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselectedDentist = searchParams.get("dentist");

  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [upcoming, setUpcoming] = useState<Appointment[]>([]);
  const [dentists, setDentists] = useState<Dentist[]>([]);
  const [loading, setLoading] = useState(true);
  const [showBooking, setShowBooking] = useState(!!preselectedDentist);
  const [booking, setBooking] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [form, setForm] = useState({
    dentist_id: preselectedDentist || "",
    appointment_date: "",
    duration_minutes: 30,
    reason: "",
    notes: "",
  });

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      const [all, up, docs] = await Promise.all([
        getAppointments(token!),
        getUpcomingAppointments(token!).catch(() => []),
        getDentists({ token: token! }).catch(() => []),
      ]);
      setAppointments(all);
      setUpcoming(up);
      setDentists(docs);
    } catch (e: any) {
      setError(e.message || "Failed to load appointments");
    } finally {
      setLoading(false);
    }
  }

  async function handleBook(e: React.FormEvent) {
    e.preventDefault();
    if (!form.dentist_id || !form.appointment_date) return;
    try {
      setBooking(true);
      setError("");
      await createAppointment(
        {
          dentist_id: form.dentist_id,
          appointment_date: form.appointment_date,
          duration_minutes: form.duration_minutes,
          reason: form.reason || undefined,
          notes: form.notes || undefined,
        },
        token!
      );
      setSuccess("Appointment booked successfully!");
      setShowBooking(false);
      setForm({ dentist_id: "", appointment_date: "", duration_minutes: 30, reason: "", notes: "" });
      await loadData();
      setTimeout(() => setSuccess(""), 3000);
    } catch (e: any) {
      setError(e.message || "Failed to book appointment");
    } finally {
      setBooking(false);
    }
  }

  async function handleCancel(id: string) {
    if (!confirm("Are you sure you want to cancel this appointment?")) return;
    try {
      await updateAppointmentStatus(id, "cancelled", undefined, token!);
      setSuccess("Appointment cancelled");
      await loadData();
      setTimeout(() => setSuccess(""), 3000);
    } catch (e: any) {
      setError(e.message || "Failed to cancel appointment");
    }
  }

  function formatDate(d: string) {
    return new Date(d).toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div />
        <button
          onClick={() => setShowBooking(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-dental-accent hover:bg-dental-accentHover text-white rounded-xl text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          Book Appointment
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-red-400 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}
      {success && (
        <div className="bg-green-500/10 border border-green-500/20 rounded-xl p-4 text-green-400 text-sm flex items-center gap-2">
          <Check className="w-4 h-4 shrink-0" /> {success}
        </div>
      )}

      {showBooking && (
        <div className="bg-dental-card border border-dental-border rounded-2xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-dental-textPrimary">Book New Appointment</h3>
            <button onClick={() => setShowBooking(false)} className="text-dental-textMuted hover:text-dental-textPrimary">
              <X className="w-5 h-5" />
            </button>
          </div>
          <form onSubmit={handleBook} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-dental-textSecondary mb-1">Dentist</label>
                <select
                  value={form.dentist_id}
                  onChange={(e) => setForm({ ...form, dentist_id: e.target.value })}
                  required
                  className="w-full px-3 py-2.5 bg-dental-input border border-dental-border rounded-xl text-dental-textPrimary focus:outline-none focus:border-dental-accent"
                >
                  <option value="">Select dentist</option>
                  {dentists.map((d) => (
                    <option key={d.id} value={d.id}>{d.full_name} — {d.specialization.join(", ") || "General"}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-dental-textSecondary mb-1">Date & Time</label>
                <input
                  type="datetime-local"
                  value={form.appointment_date}
                  onChange={(e) => setForm({ ...form, appointment_date: e.target.value })}
                  required
                  className="w-full px-3 py-2.5 bg-dental-input border border-dental-border rounded-xl text-dental-textPrimary focus:outline-none focus:border-dental-accent"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-dental-textSecondary mb-1">Duration (minutes)</label>
                <select
                  value={form.duration_minutes}
                  onChange={(e) => setForm({ ...form, duration_minutes: Number(e.target.value) })}
                  className="w-full px-3 py-2.5 bg-dental-input border border-dental-border rounded-xl text-dental-textPrimary focus:outline-none focus:border-dental-accent"
                >
                  <option value={15}>15 minutes</option>
                  <option value={30}>30 minutes</option>
                  <option value={45}>45 minutes</option>
                  <option value={60}>1 hour</option>
                  <option value={90}>1.5 hours</option>
                  <option value={120}>2 hours</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-dental-textSecondary mb-1">Reason for Visit</label>
                <input
                  type="text"
                  value={form.reason}
                  onChange={(e) => setForm({ ...form, reason: e.target.value })}
                  placeholder="e.g., Routine checkup, tooth pain"
                  className="w-full px-3 py-2.5 bg-dental-input border border-dental-border rounded-xl text-dental-textPrimary placeholder:text-dental-textMuted focus:outline-none focus:border-dental-accent"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-dental-textSecondary mb-1">Additional Notes</label>
              <textarea
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                rows={2}
                placeholder="Any additional information..."
                className="w-full px-3 py-2.5 bg-dental-input border border-dental-border rounded-xl text-dental-textPrimary placeholder:text-dental-textMuted focus:outline-none focus:border-dental-accent resize-none"
              />
            </div>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowBooking(false)}
                className="px-4 py-2 text-dental-textSecondary hover:text-dental-textPrimary transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={booking}
                className="px-6 py-2.5 bg-dental-accent hover:bg-dental-accentHover text-white rounded-xl text-sm font-medium transition-colors disabled:opacity-50"
              >
                {booking ? "Booking..." : "Book Appointment"}
              </button>
            </div>
          </form>
        </div>
      )}

      {upcoming.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-dental-textSecondary mb-3 uppercase tracking-wider">Upcoming</h3>
          <div className="space-y-3">
            {upcoming.map((apt) => (
              <div key={apt.id} className="bg-dental-card border border-dental-border rounded-2xl p-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-dental-accent/10 flex items-center justify-center">
                    <Calendar className="w-5 h-5 text-dental-accent" />
                  </div>
                  <div>
                    <p className="font-medium text-dental-textPrimary">{apt.dentist?.full_name || "Dentist"}</p>
                    <p className="text-sm text-dental-textMuted">{formatDate(apt.appointment_date)}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-2.5 py-1 rounded-full text-xs font-medium border ${STATUS_COLORS[apt.status] || "bg-gray-500/10 text-gray-400 border-gray-500/20"}`}>
                    {apt.status}
                  </span>
                  {(apt.status === "pending" || apt.status === "confirmed") && (
                    <button
                      onClick={() => handleCancel(apt.id)}
                      className="p-1.5 text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <h3 className="text-sm font-semibold text-dental-textSecondary mb-3 uppercase tracking-wider">All Appointments</h3>
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="bg-dental-card border border-dental-border rounded-2xl p-4 animate-pulse">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-dental-muted rounded-xl" />
                  <div className="flex-1">
                    <div className="h-4 bg-dental-muted rounded w-1/3 mb-2" />
                    <div className="h-3 bg-dental-muted rounded w-1/4" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : appointments.length === 0 ? (
          <div className="text-center py-12">
            <Calendar className="w-12 h-12 text-dental-textMuted mx-auto mb-3" />
            <p className="text-dental-textMuted">No appointments yet</p>
            <p className="text-dental-textMuted text-sm mt-1">Book your first appointment with a dentist</p>
          </div>
        ) : (
          <div className="space-y-3">
            {appointments.map((apt) => (
              <div key={apt.id} className="bg-dental-card border border-dental-border rounded-2xl p-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-dental-accent/10 flex items-center justify-center">
                    <Calendar className="w-5 h-5 text-dental-accent" />
                  </div>
                  <div>
                    <p className="font-medium text-dental-textPrimary">{apt.dentist?.full_name || "Dentist"}</p>
                    <p className="text-sm text-dental-textMuted">{formatDate(apt.appointment_date)}</p>
                    {apt.reason && <p className="text-xs text-dental-textMuted mt-0.5">{apt.reason}</p>}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-2.5 py-1 rounded-full text-xs font-medium border ${STATUS_COLORS[apt.status] || "bg-gray-500/10 text-gray-400 border-gray-500/20"}`}>
                    {apt.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function AppointmentsPage() {
  return (
    <AuthGate>
      <AppShell title="Appointments" subtitle="Schedule and manage your dental appointments.">
        <AppointmentsContent />
      </AppShell>
    </AuthGate>
  );
}
