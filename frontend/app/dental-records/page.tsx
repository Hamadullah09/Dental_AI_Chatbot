"use client";

import { useState, useEffect } from "react";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { useAuth } from "@/lib/auth";
import { getDentalRecords, downloadDentalRecordPdf } from "@/lib/api";
import type { DentalRecord } from "@/lib/types";
import { FileText, Download, AlertCircle, Stethoscope } from "lucide-react";

function DentalRecordsContent() {
  const { token } = useAuth();
  const [records, setRecords] = useState<DentalRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    loadRecords();
  }, []);

  async function loadRecords() {
    try {
      setLoading(true);
      const data = await getDentalRecords(token!);
      setRecords(data);
    } catch (e: any) {
      setError(e.message || "Failed to load dental records");
    } finally {
      setLoading(false);
    }
  }

  async function handleDownloadPdf(id: string) {
    try {
      const blob = await downloadDentalRecordPdf(id, token!);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dental-record-${id.slice(0, 8)}.pdf`;
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

  function DetailSection({ label, value }: { label: string; value: string | null | undefined }) {
    if (!value) return null;
    return (
      <div className="bg-dental-muted/30 rounded-xl p-3">
        <p className="text-xs text-dental-textMuted mb-1">{label}</p>
        <p className="text-sm text-dental-textPrimary whitespace-pre-line">{value}</p>
      </div>
    );
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
          {[1, 2].map((i) => (
            <div key={i} className="bg-dental-card border border-dental-border rounded-2xl p-6 animate-pulse">
              <div className="h-5 bg-dental-muted rounded w-1/3 mb-3" />
              <div className="h-4 bg-dental-muted rounded w-1/2 mb-2" />
              <div className="h-3 bg-dental-muted rounded w-2/3" />
            </div>
          ))}
        </div>
      ) : records.length === 0 ? (
        <div className="text-center py-16">
          <Stethoscope className="w-12 h-12 text-dental-textMuted mx-auto mb-3" />
          <p className="text-dental-textMuted text-lg">No dental records yet</p>
          <p className="text-dental-textMuted text-sm mt-1">Your dental history will appear here after visits</p>
        </div>
      ) : (
        <div className="space-y-4">
          {records.map((record) => (
            <div key={record.id} className="bg-dental-card border border-dental-border rounded-2xl p-6">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="font-semibold text-dental-textPrimary">
                    Dental Record
                  </h3>
                  <p className="text-sm text-dental-textMuted mt-1">
                    Recorded on {formatDate(record.created_at)}
                    {record.dentist?.full_name && ` by ${record.dentist.full_name}`}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setExpandedId(expandedId === record.id ? null : record.id)}
                    className="px-3 py-1.5 text-sm text-dental-textSecondary hover:bg-dental-muted rounded-lg transition-colors"
                  >
                    {expandedId === record.id ? "Collapse" : "Details"}
                  </button>
                  <button
                    onClick={() => handleDownloadPdf(record.id)}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-dental-accent hover:bg-dental-accentSoft rounded-lg transition-colors"
                  >
                    <Download className="w-4 h-4" />
                    PDF
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                {record.diagnoses && (
                  <div className="text-center p-2 bg-dental-muted/20 rounded-xl">
                    <p className="text-xs text-dental-textMuted">Diagnoses</p>
                    <p className="text-sm font-medium text-dental-textPrimary truncate">{record.diagnoses.split("\n")[0]}</p>
                  </div>
                )}
                {record.treatments && (
                  <div className="text-center p-2 bg-dental-muted/20 rounded-xl">
                    <p className="text-xs text-dental-textMuted">Treatments</p>
                    <p className="text-sm font-medium text-dental-textPrimary truncate">{record.treatments.split("\n")[0]}</p>
                  </div>
                )}
                {record.allergies && (
                  <div className="text-center p-2 bg-dental-muted/20 rounded-xl">
                    <p className="text-xs text-dental-textMuted">Allergies</p>
                    <p className="text-sm font-medium text-dental-textPrimary truncate">{record.allergies.split("\n")[0]}</p>
                  </div>
                )}
                {record.medications && (
                  <div className="text-center p-2 bg-dental-muted/20 rounded-xl">
                    <p className="text-xs text-dental-textMuted">Medications</p>
                    <p className="text-sm font-medium text-dental-textPrimary truncate">{record.medications.split("\n")[0]}</p>
                  </div>
                )}
              </div>

              {expandedId === record.id && (
                <div className="border-t border-dental-border pt-4 space-y-3">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <DetailSection label="Previous Problems" value={record.previous_problems} />
                    <DetailSection label="Diagnoses" value={record.diagnoses} />
                    <DetailSection label="Treatments" value={record.treatments} />
                    <DetailSection label="Surgeries" value={record.surgeries} />
                    <DetailSection label="Allergies" value={record.allergies} />
                    <DetailSection label="Medications" value={record.medications} />
                    <DetailSection label="Notes" value={record.notes} />
                    <DetailSection label="Follow-up Records" value={record.follow_up_records} />
                  </div>
                  {(record.xrays.length > 0 || record.reports.length > 0 || record.images.length > 0) && (
                    <div>
                      <p className="text-xs text-dental-textMuted mb-2">Attachments</p>
                      <div className="flex flex-wrap gap-2">
                        {record.xrays.map((x, i) => (
                          <span key={i} className="px-2 py-1 bg-dental-muted text-dental-textSecondary text-xs rounded-full">
                            X-Ray {i + 1}
                          </span>
                        ))}
                        {record.reports.map((r, i) => (
                          <span key={i} className="px-2 py-1 bg-dental-muted text-dental-textSecondary text-xs rounded-full">
                            Report {i + 1}
                          </span>
                        ))}
                        {record.images.map((img, i) => (
                          <span key={i} className="px-2 py-1 bg-dental-muted text-dental-textSecondary text-xs rounded-full">
                            Image {i + 1}
                          </span>
                        ))}
                      </div>
                    </div>
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

export default function DentalRecordsPage() {
  return (
    <AuthGate>
      <AppShell title="Dental Records" subtitle="View your complete dental history and records.">
        <DentalRecordsContent />
      </AppShell>
    </AuthGate>
  );
}
