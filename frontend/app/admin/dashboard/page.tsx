"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { AuthGate } from "@/components/AuthGate";
import { AppShell } from "@/components/AppShell";
import type { EvaluationMetricsResponse } from "@/lib/types";

export default function DashboardPage() {
  const { token } = useAuth();
  const [metrics, setMetrics] = useState<EvaluationMetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    const apiBase = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
    fetch(`${apiBase}/api/dashboard/metrics`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => {
        setMetrics(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [token]);

  return (
    <AuthGate adminOnly>
      <AppShell title="Evaluation Dashboard" subtitle="RAG performance and quality metrics">
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center h-48 text-dental-textSecondary">Loading metrics...</div>
          ) : metrics ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <MetricCard label="Total Queries" value={metrics.total_queries} />
              <MetricCard label="Avg Retrieval Latency" value={`${metrics.avg_retrieval_latency_ms}ms`} />
              <MetricCard label="Avg LLM Latency" value={`${metrics.avg_llm_latency_ms}ms`} />
              <MetricCard label="Citation Accuracy" value={`${metrics.citation_accuracy}%`} />
              <MetricCard label="User Satisfaction" value={`${metrics.user_satisfaction}%`} />
              <MetricCard label="Hallucination Rate" value={`${metrics.hallucination_rate}%`} />
              <MetricCard label="Failed Retrievals" value={metrics.failed_retrievals} />
              <div className="col-span-full rounded-2xl border border-dental-border bg-dental-card p-4">
                <h3 className="text-sm font-semibold text-dental-textPrimary mb-3">Answer Mode Breakdown</h3>
                <div className="space-y-2">
                  {Object.entries(metrics.mode_breakdown).map(([mode, count]) => (
                    <div key={mode} className="flex items-center justify-between">
                      <span className="text-sm text-dental-textSecondary">{mode}</span>
                      <span className="text-sm font-medium text-dental-textPrimary">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center text-dental-textSecondary py-12">Failed to load metrics</div>
          )}
        </div>
      </AppShell>
    </AuthGate>
  );
}

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-dental-border bg-dental-card p-4">
      <p className="text-xs text-dental-textSecondary mb-1">{label}</p>
      <p className="text-2xl font-semibold text-dental-textPrimary">{value}</p>
    </div>
  );
}
