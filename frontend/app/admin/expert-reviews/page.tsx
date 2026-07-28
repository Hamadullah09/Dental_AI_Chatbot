"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { AuthGate } from "@/components/AuthGate";
import { AppShell } from "@/components/AppShell";
import { sampleReviewableConversations, submitExpertReview, getExpertReviewSummary } from "@/lib/api";
import type { ReviewableConversation, ExpertReviewSummary, FaithfulnessRating, SafetyRating, CitationAccuracyRating } from "@/lib/types";
import { CheckCircle2, ClipboardCheck } from "lucide-react";

const FAITHFULNESS_OPTIONS: { value: FaithfulnessRating; label: string }[] = [
  { value: "faithful", label: "Faithful" },
  { value: "partially_faithful", label: "Partially faithful" },
  { value: "unfaithful", label: "Unfaithful" },
];
const SAFETY_OPTIONS: { value: SafetyRating; label: string }[] = [
  { value: "safe", label: "Safe" },
  { value: "concerning", label: "Concerning" },
  { value: "unsafe", label: "Unsafe" },
];
const CITATION_OPTIONS: { value: CitationAccuracyRating; label: string }[] = [
  { value: "accurate", label: "Accurate" },
  { value: "partially_accurate", label: "Partially accurate" },
  { value: "inaccurate", label: "Inaccurate" },
  { value: "not_applicable", label: "N/A" },
];

function RatingGroup<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T | null;
  onChange: (v: T) => void;
}) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-dental-textSecondary mb-1.5">{label}</p>
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
              value === opt.value
                ? "bg-dental-accent text-white"
                : "bg-dental-muted text-dental-textSecondary hover:bg-dental-accentSoft hover:text-dental-accent"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function ExpertReviewsPage() {
  const { token } = useAuth();
  const [queue, setQueue] = useState<ReviewableConversation[]>([]);
  const [summary, setSummary] = useState<ExpertReviewSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [faithfulness, setFaithfulness] = useState<FaithfulnessRating | null>(null);
  const [safety, setSafety] = useState<SafetyRating | null>(null);
  const [citationAccuracy, setCitationAccuracy] = useState<CitationAccuracyRating | null>(null);
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (!token) return;
    load();
  }, [token]);

  async function load() {
    try {
      setLoading(true);
      const [conversations, summaryData] = await Promise.all([
        sampleReviewableConversations(token!),
        getExpertReviewSummary(token!),
      ]);
      setQueue(conversations);
      setSummary(summaryData);
    } catch (e: any) {
      setError(e.message || "Failed to load review queue");
    } finally {
      setLoading(false);
    }
  }

  const current = queue[0];

  async function handleSubmit() {
    if (!current || !faithfulness || !safety || !citationAccuracy) return;
    setSubmitting(true);
    try {
      await submitExpertReview(current.message_id, token!, {
        faithfulness,
        safety,
        citation_accuracy: citationAccuracy,
        notes: notes || undefined,
      });
      setQueue((q) => q.slice(1));
      setFaithfulness(null);
      setSafety(null);
      setCitationAccuracy(null);
      setNotes("");
      const newSummary = await getExpertReviewSummary(token!);
      setSummary(newSummary);
    } catch (e: any) {
      setError(e.message || "Failed to submit review");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthGate adminOnly>
      <AppShell title="Expert Reviews" subtitle="Sample real conversations against a faithfulness, safety, and citation rubric">
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {error && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-600 dark:text-red-300">{error}</div>
          )}

          {summary && (
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-dental-border bg-dental-card p-4">
                <p className="text-xs text-dental-textSecondary mb-1">Reviewed / Unreviewed</p>
                <p className="text-xl font-semibold text-dental-textPrimary">
                  {summary.total_reviewed} / {summary.total_unreviewed}
                </p>
              </div>
              <div className="rounded-2xl border border-dental-border bg-dental-card p-4">
                <p className="text-xs text-dental-textSecondary mb-1">Faithful</p>
                <p className="text-xl font-semibold text-dental-textPrimary">{summary.faithful_pct ?? "—"}{summary.faithful_pct !== null && "%"}</p>
              </div>
              <div className="rounded-2xl border border-dental-border bg-dental-card p-4">
                <p className="text-xs text-dental-textSecondary mb-1">Safe</p>
                <p className="text-xl font-semibold text-dental-textPrimary">{summary.safe_pct ?? "—"}{summary.safe_pct !== null && "%"}</p>
              </div>
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center h-48 text-dental-textSecondary">Loading review queue...</div>
          ) : !current ? (
            <div className="text-center text-dental-textSecondary py-12">
              <ClipboardCheck className="w-12 h-12 mx-auto mb-3 text-dental-textMuted" />
              <p className="text-base font-medium text-dental-textPrimary">Queue is clear</p>
              <p className="mt-1 text-sm">Every sampled conversation has been reviewed. Check back once more chats come in.</p>
            </div>
          ) : (
            <div className="rounded-2xl border border-dental-border bg-dental-card p-6 space-y-5">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-dental-textSecondary mb-1">Question</p>
                <p className="text-dental-textPrimary">{current.question || "(no question found)"}</p>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-dental-textSecondary mb-1">
                  Answer {current.answer_mode && <span className="font-mono normal-case text-dental-textMuted">· {current.answer_mode}</span>}
                </p>
                <p className="text-dental-textPrimary whitespace-pre-line">{current.answer}</p>
              </div>
              {current.sources.length > 0 && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-dental-textSecondary mb-1">Sources</p>
                  <ul className="text-sm text-dental-textSecondary list-disc list-inside">
                    {current.sources.map((s, i) => (
                      <li key={i}>{String((s as any).document_name || JSON.stringify(s))}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="border-t border-dental-border pt-5 space-y-4">
                <RatingGroup label="Faithfulness" options={FAITHFULNESS_OPTIONS} value={faithfulness} onChange={setFaithfulness} />
                <RatingGroup label="Safety" options={SAFETY_OPTIONS} value={safety} onChange={setSafety} />
                <RatingGroup label="Citation accuracy" options={CITATION_OPTIONS} value={citationAccuracy} onChange={setCitationAccuracy} />
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-dental-textSecondary mb-1.5">Notes (optional)</p>
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    rows={2}
                    className="w-full px-3 py-2.5 bg-dental-input border border-dental-border rounded-xl text-dental-textPrimary placeholder:text-dental-textMuted focus:outline-none focus:border-dental-accent resize-none"
                    placeholder="Anything a future reviewer should know about this call"
                  />
                </div>
                <button
                  type="button"
                  disabled={submitting || !faithfulness || !safety || !citationAccuracy}
                  onClick={handleSubmit}
                  className="inline-flex items-center gap-2 rounded-xl bg-dental-accent px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-dental-accentHover disabled:opacity-50"
                >
                  <CheckCircle2 className="h-4 w-4" /> Submit review
                </button>
                <p className="text-xs text-dental-textMuted">{queue.length - 1} more in this batch</p>
              </div>
            </div>
          )}
        </div>
      </AppShell>
    </AuthGate>
  );
}
