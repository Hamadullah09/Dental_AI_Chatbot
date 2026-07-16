"use client";

import { useState, useEffect } from "react";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { useAuth } from "@/lib/auth";
import { getPrescriptions, downloadPrescriptionPdf } from "@/lib/api";
import type { Prescription } from "@/lib/types";
import { Pill, Download, Calendar, FileText, AlertCircle } from "lucide-react";

function PrescriptionsContent() {
  const { token } = useAuth();
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    loadPrescriptions();
  }, []);

  async function loadPrescriptions() {
    try {
      setLoading(true);
      const data = await getPrescriptions(token!);
      setPrescriptions(data);
    } catch (e: any) {
      setError(e.message || "Failed to load prescriptions");
    } finally {
      setLoading(false);
    }
  }

  async function handleDownloadPdf(id: string, name: string) {
    try {
      const blob = await downloadPrescriptionPdf(id, token!);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `prescription-${name}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e.message || "Failed to download PDF");
    }
  }

  function formatDate(d: string) {
    return new Date(d).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-red-400 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-dental-card border border-dental-border rounded-2xl p-6 animate-pulse">
              <div className="h-5 bg-dental-muted rounded w-1/3 mb-3" />
              <div className="h-4 bg-dental-muted rounded w-1/2 mb-2" />
              <div className="h-3 bg-dental-muted rounded w-2/3" />
            </div>
          ))}
        </div>
      ) : prescriptions.length === 0 ? (
        <div className="text-center py-16">
          <Pill className="w-12 h-12 text-dental-textMuted mx-auto mb-3" />
          <p className="text-dental-textMuted text-lg">No prescriptions yet</p>
          <p className="text-dental-textMuted text-sm mt-1">Your prescriptions will appear here after a dental visit</p>
        </div>
      ) : (
        <div className="space-y-4">
          {prescriptions.map((rx) => (
            <div key={rx.id} className="bg-dental-card border border-dental-border rounded-2xl p-6">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="font-semibold text-dental-textPrimary text-lg">{rx.diagnosis}</h3>
                  <p className="text-sm text-dental-textMuted mt-1">
                    Prescribed by {rx.dentist?.full_name || "Dentist"} on {formatDate(rx.created_at)}
                  </p>
                </div>
                <button
                  onClick={() => handleDownloadPdf(rx.id, rx.diagnosis.replace(/\s+/g, "-"))}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-dental-accent hover:bg-dental-accentSoft rounded-lg transition-colors"
                >
                  <Download className="w-4 h-4" />
                  PDF
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                <div className="bg-dental-muted/30 rounded-xl p-3">
                  <p className="text-xs text-dental-textMuted mb-1">Medicines</p>
                  <p className="text-sm text-dental-textPrimary whitespace-pre-line">{rx.medicines}</p>
                </div>
                <div className="bg-dental-muted/30 rounded-xl p-3">
                  <p className="text-xs text-dental-textMuted mb-1">Dosage & Frequency</p>
                  <p className="text-sm text-dental-textPrimary">{rx.dosage} — {rx.frequency}</p>
                </div>
                <div className="bg-dental-muted/30 rounded-xl p-3">
                  <p className="text-xs text-dental-textMuted mb-1">Duration</p>
                  <p className="text-sm text-dental-textPrimary">{rx.duration}</p>
                </div>
                {rx.follow_up_date && (
                  <div className="bg-dental-muted/30 rounded-xl p-3">
                    <p className="text-xs text-dental-textMuted mb-1">Follow-up</p>
                    <p className="text-sm text-dental-textPrimary flex items-center gap-1.5">
                      <Calendar className="w-3.5 h-3.5" />
                      {formatDate(rx.follow_up_date)}
                    </p>
                  </div>
                )}
              </div>

              {(rx.instructions || rx.notes) && (
                <div className="border-t border-dental-border pt-3">
                  {rx.instructions && (
                    <p className="text-sm text-dental-textSecondary">
                      <span className="font-medium">Instructions:</span> {rx.instructions}
                    </p>
                  )}
                  {rx.notes && (
                    <p className="text-sm text-dental-textSecondary mt-1">
                      <span className="font-medium">Notes:</span> {rx.notes}
                    </p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PrescriptionsPage() {
  return (
    <AuthGate>
      <AppShell title="Prescriptions" subtitle="View and download your dental prescriptions.">
        <PrescriptionsContent />
      </AppShell>
    </AuthGate>
  );
}
