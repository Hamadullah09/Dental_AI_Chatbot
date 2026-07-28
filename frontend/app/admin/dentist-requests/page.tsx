"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { AuthGate } from "@/components/AuthGate";
import { AppShell } from "@/components/AppShell";
import { listDentistRequests, approveDentistRequest, rejectDentistRequest } from "@/lib/api";
import type { DentistVerificationRequest } from "@/lib/types";
import { CheckCircle2, XCircle } from "lucide-react";

export default function DentistRequestsPage() {
  const { token } = useAuth();
  const [requests, setRequests] = useState<DentistVerificationRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyUserId, setBusyUserId] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    loadRequests();
  }, [token]);

  async function loadRequests() {
    try {
      setLoading(true);
      const data = await listDentistRequests(token!, "pending");
      setRequests(data);
    } catch (e: any) {
      setError(e.message || "Failed to load dentist requests");
    } finally {
      setLoading(false);
    }
  }

  async function handleApprove(userId: string) {
    setBusyUserId(userId);
    try {
      await approveDentistRequest(userId, token!);
      setRequests((current) => current.filter((r) => r.user_id !== userId));
    } catch (e: any) {
      setError(e.message || "Failed to approve request");
    } finally {
      setBusyUserId(null);
    }
  }

  async function handleReject(userId: string) {
    const notes = window.prompt("Reason for rejecting this request (shown in the audit log):") || undefined;
    setBusyUserId(userId);
    try {
      await rejectDentistRequest(userId, token!, notes);
      setRequests((current) => current.filter((r) => r.user_id !== userId));
    } catch (e: any) {
      setError(e.message || "Failed to reject request");
    } finally {
      setBusyUserId(null);
    }
  }

  return (
    <AuthGate adminOnly>
      <AppShell title="Dentist Requests" subtitle="Verify credentials before granting clinical access">
        <div className="flex-1 overflow-y-auto p-6">
          {error && (
            <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-600 dark:text-red-300">
              {error}
            </div>
          )}
          {loading ? (
            <div className="flex items-center justify-center h-48 text-dental-textSecondary">Loading requests...</div>
          ) : requests.length === 0 ? (
            <div className="text-center text-dental-textSecondary py-12">
              <p className="text-base font-medium text-dental-textPrimary">No pending dentist requests</p>
              <p className="mt-1 text-sm">New requests appear here as soon as someone registers with the dentist role.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {requests.map((r) => (
                <div key={r.user_id} className="rounded-2xl border border-dental-border bg-dental-card p-4 flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <p className="font-semibold text-dental-textPrimary truncate">{r.full_name || r.email}</p>
                    <p className="text-sm text-dental-textSecondary truncate">{r.email}</p>
                    <p className="text-sm text-dental-textSecondary mt-1">
                      License: <span className="font-mono">{r.license_number || "—"}</span>
                      {r.clinic_name && <> · {r.clinic_name}</>}
                    </p>
                    {r.requested_at && (
                      <p className="text-xs text-dental-textMuted mt-1">Requested {new Date(r.requested_at).toLocaleString()}</p>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <button
                      type="button"
                      disabled={busyUserId === r.user_id}
                      onClick={() => handleApprove(r.user_id)}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-dental-accent px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-dental-accentHover disabled:opacity-50"
                    >
                      <CheckCircle2 className="h-4 w-4" /> Approve
                    </button>
                    <button
                      type="button"
                      disabled={busyUserId === r.user_id}
                      onClick={() => handleReject(r.user_id)}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-dental-border px-3 py-2 text-sm font-semibold text-dental-textPrimary transition-colors hover:bg-dental-border disabled:opacity-50"
                    >
                      <XCircle className="h-4 w-4" /> Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </AppShell>
    </AuthGate>
  );
}
