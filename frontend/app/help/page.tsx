"use client";

import { useState, useEffect } from "react";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { useAuth } from "@/lib/auth";
import { getHelpArticles, submitSupportTicket } from "@/lib/api";
import type { HelpArticle } from "@/lib/types";
import {
  HelpCircle,
  Search,
  ChevronDown,
  ChevronUp,
  MessageSquare,
  Send,
  AlertCircle,
  Check,
  BookOpen,
} from "lucide-react";

function HelpContent() {
  const { token } = useAuth();
  const [articles, setArticles] = useState<HelpArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showContact, setShowContact] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [ticket, setTicket] = useState({
    subject: "",
    message: "",
    category: "general",
    priority: "normal",
  });

  useEffect(() => {
    loadArticles();
  }, []);

  async function loadArticles() {
    try {
      setLoading(true);
      const data = await getHelpArticles(token!);
      setArticles(data);
    } catch (e: any) {
      setError(e.message || "Failed to load help articles");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmitTicket(e: React.FormEvent) {
    e.preventDefault();
    if (!ticket.subject || !ticket.message) return;
    try {
      setSubmitting(true);
      setError("");
      await submitSupportTicket(ticket, token!);
      setSuccess("Support ticket submitted successfully! We'll get back to you soon.");
      setShowContact(false);
      setTicket({ subject: "", message: "", category: "general", priority: "normal" });
      setTimeout(() => setSuccess(""), 5000);
    } catch (e: any) {
      setError(e.message || "Failed to submit ticket");
    } finally {
      setSubmitting(false);
    }
  }

  const filtered = articles.filter(
    (a) =>
      !search ||
      a.title.toLowerCase().includes(search.toLowerCase()) ||
      a.content.toLowerCase().includes(search.toLowerCase()) ||
      a.category.toLowerCase().includes(search.toLowerCase())
  );

  const categories = [...new Set(articles.map((a) => a.category))];

  return (
    <div className="space-y-6">
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

      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dental-textMuted" />
          <input
            type="text"
            placeholder="Search help articles..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-dental-input border border-dental-border rounded-xl text-dental-textPrimary placeholder:text-dental-textMuted focus:outline-none focus:border-dental-accent"
          />
        </div>
        <button
          onClick={() => setShowContact(!showContact)}
          className="flex items-center gap-2 px-4 py-2.5 bg-dental-accent hover:bg-dental-accentHover text-white rounded-xl text-sm font-medium transition-colors"
        >
          <MessageSquare className="w-4 h-4" />
          Contact Support
        </button>
      </div>

      {showContact && (
        <div className="bg-dental-card border border-dental-border rounded-2xl p-6">
          <h3 className="text-lg font-semibold text-dental-textPrimary mb-4">Contact Support</h3>
          <form onSubmit={handleSubmitTicket} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-dental-textSecondary mb-1">Category</label>
                <select
                  value={ticket.category}
                  onChange={(e) => setTicket({ ...ticket, category: e.target.value })}
                  className="w-full px-3 py-2.5 bg-dental-input border border-dental-border rounded-xl text-dental-textPrimary focus:outline-none focus:border-dental-accent"
                >
                  <option value="general">General Inquiry</option>
                  <option value="technical">Technical Issue</option>
                  <option value="billing">Billing</option>
                  <option value="feature_request">Feature Request</option>
                  <option value="bug_report">Bug Report</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-dental-textSecondary mb-1">Priority</label>
                <select
                  value={ticket.priority}
                  onChange={(e) => setTicket({ ...ticket, priority: e.target.value })}
                  className="w-full px-3 py-2.5 bg-dental-input border border-dental-border rounded-xl text-dental-textPrimary focus:outline-none focus:border-dental-accent"
                >
                  <option value="low">Low</option>
                  <option value="normal">Normal</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-dental-textSecondary mb-1">Subject</label>
              <input
                type="text"
                value={ticket.subject}
                onChange={(e) => setTicket({ ...ticket, subject: e.target.value })}
                required
                placeholder="Brief description of your issue"
                className="w-full px-3 py-2.5 bg-dental-input border border-dental-border rounded-xl text-dental-textPrimary placeholder:text-dental-textMuted focus:outline-none focus:border-dental-accent"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-dental-textSecondary mb-1">Message</label>
              <textarea
                value={ticket.message}
                onChange={(e) => setTicket({ ...ticket, message: e.target.value })}
                required
                rows={4}
                placeholder="Describe your issue in detail..."
                className="w-full px-3 py-2.5 bg-dental-input border border-dental-border rounded-xl text-dental-textPrimary placeholder:text-dental-textMuted focus:outline-none focus:border-dental-accent resize-none"
              />
            </div>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowContact(false)}
                className="px-4 py-2 text-dental-textSecondary hover:text-dental-textPrimary transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="flex items-center gap-2 px-6 py-2.5 bg-dental-accent hover:bg-dental-accentHover text-white rounded-xl text-sm font-medium transition-colors disabled:opacity-50"
              >
                <Send className="w-4 h-4" />
                {submitting ? "Submitting..." : "Submit Ticket"}
              </button>
            </div>
          </form>
        </div>
      )}

      {categories.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setSearch(search === cat ? "" : cat)}
              className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                search === cat
                  ? "bg-dental-accent text-white"
                  : "bg-dental-muted text-dental-textSecondary hover:bg-dental-accentSoft hover:text-dental-accent"
              }`}
            >
              {cat.replace(/_/g, " ")}
            </button>
          ))}
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-dental-card border border-dental-border rounded-2xl p-5 animate-pulse">
              <div className="h-5 bg-dental-muted rounded w-2/3 mb-2" />
              <div className="h-3 bg-dental-muted rounded w-full mb-2" />
              <div className="h-3 bg-dental-muted rounded w-4/5" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16">
          <BookOpen className="w-12 h-12 text-dental-textMuted mx-auto mb-3" />
          <p className="text-dental-textMuted text-lg">No articles found</p>
          <p className="text-dental-textMuted text-sm mt-1">
            {search ? "Try different search terms" : "Help articles will appear here"}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((article) => (
            <div key={article.id} className="bg-dental-card border border-dental-border rounded-2xl overflow-hidden">
              <button
                onClick={() => setExpandedId(expandedId === article.id ? null : article.id)}
                className="w-full px-6 py-4 flex items-center justify-between text-left hover:bg-dental-muted/20 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <HelpCircle className="w-5 h-5 text-dental-accent shrink-0" />
                  <div className="min-w-0">
                    <h3 className="font-medium text-dental-textPrimary truncate">{article.title}</h3>
                    <p className="text-xs text-dental-textMuted mt-0.5">
                      {article.category.replace(/_/g, " ")} • {article.view_count} views
                    </p>
                  </div>
                </div>
                {expandedId === article.id ? (
                  <ChevronUp className="w-5 h-5 text-dental-textMuted shrink-0" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-dental-textMuted shrink-0" />
                )}
              </button>
              {expandedId === article.id && (
                <div className="px-6 pb-5 border-t border-dental-border pt-4">
                  <div className="prose prose-sm max-w-none text-dental-textSecondary whitespace-pre-line">
                    {article.content}
                  </div>
                  {article.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-4">
                      {article.tags.map((tag) => (
                        <span key={tag} className="px-2 py-0.5 bg-dental-muted text-dental-textMuted text-xs rounded-full">
                          {tag}
                        </span>
                      ))}
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

export default function HelpPage() {
  return (
    <AuthGate>
      <AppShell title="Help Center" subtitle="Find answers and get support.">
        <HelpContent />
      </AppShell>
    </AuthGate>
  );
}
