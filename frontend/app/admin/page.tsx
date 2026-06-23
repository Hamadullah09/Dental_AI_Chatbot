"use client";

import { ChangeEvent, useCallback, useEffect, useState } from "react";
import { Download, FileUp, RefreshCw, Trash2, Database, ShieldAlert, Sparkles, Wand2, ScrollText } from "lucide-react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import {
  deleteDocument,
  downloadDatasetReviewCsv,
  generateDataset,
  getDocumentIngestionLogs,
  getDatasetGenerationStatus,
  getDocuments,
  isInvalidTokenError,
  reingestDocument,
  uploadDocument
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DatasetGenerationStatus, DocumentIngestionLog, DocumentItem } from "@/lib/types";

export default function AdminPage() {
  const router = useRouter();
  const { token, logout } = useAuth();
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [openLogDocumentId, setOpenLogDocumentId] = useState<string | null>(null);
  const [logsByDocument, setLogsByDocument] = useState<Record<string, DocumentIngestionLog[]>>({});
  const [file, setFile] = useState<File | null>(null);
  const [bookTitle, setBookTitle] = useState("");
  const [authorOrSource, setAuthorOrSource] = useState("");
  const [year, setYear] = useState("");
  const [edition, setEdition] = useState("");
  const [documentType, setDocumentType] = useState("textbook");
  const [trustLevel, setTrustLevel] = useState("high");
  const [specialty, setSpecialty] = useState("");
  const [language, setLanguage] = useState("English");
  const [reviewStatus, setReviewStatus] = useState("approved");
  const [status, setStatus] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [datasetLimit, setDatasetLimit] = useState(25);
  const [examplesPerChunk, setExamplesPerChunk] = useState(5);
  const [datasetDocumentId, setDatasetDocumentId] = useState("");
  const [datasetStatus, setDatasetStatus] = useState<DatasetGenerationStatus | null>(null);
  const [isGeneratingDataset, setIsGeneratingDataset] = useState(false);
  const canDownloadDataset = Boolean(datasetStatus?.generated_items && datasetStatus.state !== "running" && datasetStatus.state !== "queued");

  const handleError = useCallback((error: unknown, fallback: string) => {
    if (isInvalidTokenError(error)) {
      logout();
      router.replace("/login");
      return "Your login session expired. Please sign in again.";
    }
    return error instanceof Error ? error.message : fallback;
  }, [logout, router]);

  const loadDocuments = useCallback(async () => {
    if (!token) return [];
    try {
      const nextDocuments = await getDocuments(token);
      setDocuments(nextDocuments);
      return nextDocuments;
    } catch (error) {
      setStatus(handleError(error, "Could not load documents"));
      return [];
    }
  }, [handleError, token]);

  const loadDocumentLogs = useCallback(async (documentId: string) => {
    if (!token) return;
    try {
      const logs = await getDocumentIngestionLogs(documentId, token);
      setLogsByDocument((current) => ({ ...current, [documentId]: logs }));
    } catch (error) {
      setStatus(handleError(error, "Could not load ingestion logs"));
    }
  }, [handleError, token]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const loadDatasetStatus = useCallback(async () => {
    if (!token) return;
    try {
      const nextStatus = await getDatasetGenerationStatus(token);
      setDatasetStatus(nextStatus);
      setIsGeneratingDataset(nextStatus.state === "running" || nextStatus.state === "queued");
    } catch (error) {
      setStatus(handleError(error, "Could not load dataset generation status"));
    }
  }, [handleError, token]);

  useEffect(() => {
    loadDatasetStatus();
  }, [loadDatasetStatus]);

  useEffect(() => {
    if (!token || !isGeneratingDataset) return;
    const timer = window.setInterval(loadDatasetStatus, 3000);
    return () => window.clearInterval(timer);
  }, [isGeneratingDataset, loadDatasetStatus, token]);

  function pollDocuments() {
    let attempts = 0;
    const timer = window.setInterval(async () => {
      attempts += 1;
      const nextDocuments = await loadDocuments();
      if (openLogDocumentId) {
        await loadDocumentLogs(openLogDocumentId);
      }
      const stillProcessing = nextDocuments.some((doc) => doc.status === "processing");
      if (!stillProcessing || attempts >= 240) {
        window.clearInterval(timer);
        if (attempts >= 240) {
          setStatus("Refresh documents to check final ingestion status.");
        }
      }
    }, 3000);
  }

  async function toggleLogs(documentId: string) {
    const nextDocumentId = openLogDocumentId === documentId ? null : documentId;
    setOpenLogDocumentId(nextDocumentId);
    if (nextDocumentId) {
      await loadDocumentLogs(nextDocumentId);
    }
  }

  async function onUpload() {
    if (!token || !file) return;
    setIsUploading(true);
    setStatus("Uploading PDF...");
    try {
      await uploadDocument(file, token, {
        book_title: bookTitle,
        author_or_source: authorOrSource,
        year,
        edition,
        document_type: documentType,
        trust_level: trustLevel,
        specialty,
        language,
        review_status: reviewStatus
      });
      setFile(null);
      setBookTitle("");
      setAuthorOrSource("");
      setYear("");
      setEdition("");
      setSpecialty("");
      setStatus("Upload accepted. Ingestion is running in the background.");
      await loadDocuments();
      pollDocuments();
    } catch (error) {
      setStatus(handleError(error, "Upload failed"));
    } finally {
      setIsUploading(false);
    }
  }

  async function onReingest(documentId: string) {
    if (!token) return;
    setStatus("Re-ingest started. This may take a few minutes for large PDFs.");
    try {
      await reingestDocument(documentId, token);
      await loadDocuments();
      pollDocuments();
    } catch (error) {
      setStatus(handleError(error, "Re-ingest failed"));
    }
  }

  async function onDelete(documentId: string) {
    if (!token) return;
    setStatus("Deleting document...");
    try {
      await deleteDocument(documentId, token);
      await loadDocuments();
      setStatus("Document deleted.");
    } catch (error) {
      setStatus(handleError(error, "Delete failed"));
    }
  }

  async function onGenerateDataset() {
    if (!token) return;
    setIsGeneratingDataset(true);
    setStatus("Q&A dataset generation queued...");
    try {
      const response = await generateDataset(token, {
        document_id: datasetDocumentId || null,
        limit: datasetLimit,
        examples_per_chunk: examplesPerChunk,
        min_quality: 0.6,
        include_noisy: false
      });
      setDatasetStatus(response);
      setStatus(response.message || "Dataset generation started.");
      window.setTimeout(loadDatasetStatus, 2000);
    } catch (error) {
      setIsGeneratingDataset(false);
      setStatus(handleError(error, "Dataset generation failed to start"));
    }
  }

  async function onDownloadDataset() {
    if (!token) return;
    setStatus("Preparing expert review CSV...");
    try {
      const blob = await downloadDatasetReviewCsv(token);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "Database Q&A.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setStatus("Expert review CSV downloaded.");
    } catch (error) {
      setStatus(handleError(error, "Could not download expert review CSV"));
    }
  }

  return (
    <AuthGate adminOnly>
      <AppShell title="Admin Workspace" subtitle="Upload, re-ingest, and manage dental knowledge PDFs.">
        <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 bg-dental-darkBg text-dental-textPrimary h-full">
          
          {/* Upload Panel */}
          <section className="p-6 bg-dental-card border border-dental-border rounded-2xl space-y-4 shadow-xl max-w-4xl mx-auto fade-in">
            <div className="flex items-center gap-2">
              <Database className="text-dental-accent w-5 h-5" />
              <h2 className="text-base font-bold text-dental-textPrimary">Upload Dental Clinical Source (PDF)</h2>
            </div>
            
            <p className="text-xs text-dental-textSecondary leading-relaxed bg-dental-darkBg/60 border border-dental-border/50 p-3.5 rounded-xl">
              Add dental textbook or guideline metadata below. The parsing engine extracts pages, chunks and embeds the text content, and indexes points in Qdrant for RAG retrievals.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-dental-textSecondary font-semibold uppercase tracking-wider">Book or Article Title</span>
                <input className="w-full bg-dental-darkBg border border-dental-border rounded-xl py-2 px-3 text-xs text-dental-textPrimary placeholder:text-dental-textSecondary focus:outline-none focus:border-dental-accent" value={bookTitle} onChange={(event) => setBookTitle(event.target.value)} placeholder="Dental Caries Textbook" />
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-dental-textSecondary font-semibold uppercase tracking-wider">Author / Publisher Source</span>
                <input className="w-full bg-dental-darkBg border border-dental-border rounded-xl py-2 px-3 text-xs text-dental-textPrimary placeholder:text-dental-textSecondary focus:outline-none focus:border-dental-accent" value={authorOrSource} onChange={(event) => setAuthorOrSource(event.target.value)} placeholder="WHO / Author name" />
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-dental-textSecondary font-semibold uppercase tracking-wider">Publication Year</span>
                <input className="w-full bg-dental-darkBg border border-dental-border rounded-xl py-2 px-3 text-xs text-dental-textPrimary placeholder:text-dental-textSecondary focus:outline-none focus:border-dental-accent" type="number" value={year} onChange={(event) => setYear(event.target.value)} placeholder="2022" min="1800" max="2100" />
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-dental-textSecondary font-semibold uppercase tracking-wider">Edition</span>
                <input className="w-full bg-dental-darkBg border border-dental-border rounded-xl py-2 px-3 text-xs text-dental-textPrimary placeholder:text-dental-textSecondary focus:outline-none focus:border-dental-accent" value={edition} onChange={(event) => setEdition(event.target.value)} placeholder="3rd edition" />
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-dental-textSecondary font-semibold uppercase tracking-wider">Document Type</span>
                <select className="w-full bg-dental-darkBg border border-dental-border rounded-xl py-2.5 px-3 text-xs text-dental-textPrimary focus:outline-none focus:border-dental-accent" value={documentType} onChange={(event) => setDocumentType(event.target.value)}>
                  <option value="textbook">Textbook</option>
                  <option value="guideline">Guideline</option>
                  <option value="patient_education">Patient education</option>
                  <option value="research_article">Research article</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-dental-textSecondary font-semibold uppercase tracking-wider">Trust Level Filter</span>
                <select className="w-full bg-dental-darkBg border border-dental-border rounded-xl py-2.5 px-3 text-xs text-dental-textPrimary focus:outline-none focus:border-dental-accent" value={trustLevel} onChange={(event) => setTrustLevel(event.target.value)}>
                  <option value="high">High Trust (Peer-reviewed)</option>
                  <option value="medium">Medium Trust</option>
                  <option value="low">Low Trust (General context)</option>
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-dental-textSecondary font-semibold uppercase tracking-wider">Clinical Specialty</span>
                <input className="w-full bg-dental-darkBg border border-dental-border rounded-xl py-2 px-3 text-xs text-dental-textPrimary placeholder:text-dental-textSecondary focus:outline-none focus:border-dental-accent" value={specialty} onChange={(event) => setSpecialty(event.target.value)} placeholder="Oral medicine / Surgery" />
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-dental-textSecondary font-semibold uppercase tracking-wider">Language</span>
                <input className="w-full bg-dental-darkBg border border-dental-border rounded-xl py-2 px-3 text-xs text-dental-textPrimary placeholder:text-dental-textSecondary focus:outline-none focus:border-dental-accent" value={language} onChange={(event) => setLanguage(event.target.value)} placeholder="English" />
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-dental-textSecondary font-semibold uppercase tracking-wider">Review Status</span>
                <select className="w-full bg-dental-darkBg border border-dental-border rounded-xl py-2.5 px-3 text-xs text-dental-textPrimary focus:outline-none focus:border-dental-accent" value={reviewStatus} onChange={(event) => setReviewStatus(event.target.value)}>
                  <option value="unreviewed">Unreviewed</option>
                  <option value="reviewed">Reviewed</option>
                  <option value="approved">Approved (Active in RAG)</option>
                  <option value="rejected">Rejected</option>
                </select>
              </div>
            </div>

            <div className="pt-2 border-t border-dental-border/40 flex flex-col sm:flex-row gap-3 items-center justify-between">
              <input
                className="w-full sm:w-auto bg-dental-darkBg border border-dental-border rounded-xl py-2 px-3 text-xs text-dental-textPrimary focus:outline-none"
                type="file"
                accept="application/pdf"
                onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] || null)}
              />
              <div className="flex gap-2 w-full sm:w-auto">
                <button 
                  onClick={onUpload} 
                  disabled={!file || isUploading}
                  className="flex-1 sm:flex-initial flex items-center justify-center gap-2 py-2 px-5 bg-dental-accent hover:bg-dental-accentHover text-white rounded-xl text-xs font-bold transition-all shadow-md disabled:opacity-40"
                >
                  <FileUp size={15} />
                  {isUploading ? "Uploading..." : "Upload File"}
                </button>
                <button 
                  onClick={loadDocuments}
                  className="flex-1 sm:flex-initial flex items-center justify-center gap-2 py-2 px-5 bg-dental-border hover:bg-dental-card border border-dental-border text-dental-textPrimary rounded-xl text-xs font-semibold transition-all"
                >
                  <RefreshCw size={15} />
                  Refresh List
                </button>
              </div>
            </div>
          </section>

          {/* Dataset Generation */}
          <section className="p-6 bg-dental-card border border-dental-border rounded-2xl space-y-4 shadow-xl max-w-4xl mx-auto">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Wand2 className="text-dental-accent w-5 h-5" />
                  <h2 className="text-base font-bold text-dental-textPrimary">Generate Draft Q&A Dataset</h2>
                </div>
                <p className="text-xs text-dental-textSecondary leading-relaxed">
                  Select a PDF, then create expert-review draft Q&A rows from its chunks. Existing chunks are skipped, and missing chunks are generated automatically.
                </p>
              </div>
              <div className="flex flex-col sm:flex-row gap-2">
                <button
                  type="button"
                  onClick={onGenerateDataset}
                  disabled={isGeneratingDataset}
                  className="flex items-center justify-center gap-2 py-2.5 px-5 bg-dental-accent hover:bg-dental-accentHover text-white rounded-xl text-xs font-bold transition-all shadow-md disabled:opacity-40"
                >
                  <Wand2 size={15} />
                  {isGeneratingDataset ? "Generating..." : "Generate Q&A"}
                </button>
                <button
                  type="button"
                  onClick={onDownloadDataset}
                  disabled={!canDownloadDataset}
                  className="flex items-center justify-center gap-2 py-2.5 px-5 bg-dental-border hover:bg-dental-card border border-dental-border text-dental-textPrimary rounded-xl text-xs font-bold transition-all disabled:opacity-40"
                >
                  <Download size={15} />
                  Download CSV
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <label className="flex flex-col gap-1 sm:col-span-3">
                <span className="text-[10px] text-dental-textSecondary font-semibold uppercase tracking-wider">PDF Chunks To Use</span>
                <select
                  className="w-full bg-dental-darkBg border border-dental-border rounded-xl py-2.5 px-3 text-xs text-dental-textPrimary focus:outline-none focus:border-dental-accent"
                  value={datasetDocumentId}
                  onChange={(event) => setDatasetDocumentId(event.target.value)}
                  disabled={isGeneratingDataset}
                >
                  <option value="">All ready PDFs</option>
                  {documents.map((doc) => (
                    <option key={doc.id} value={doc.id}>
                      {(doc.title || doc.original_filename)} ({doc.chunk_count} chunks, {doc.status})
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-dental-textSecondary font-semibold uppercase tracking-wider">Chunk Limit</span>
                <input
                  className="w-full bg-dental-darkBg border border-dental-border rounded-xl py-2 px-3 text-xs text-dental-textPrimary focus:outline-none focus:border-dental-accent"
                  type="number"
                  min={1}
                  max={500}
                  value={datasetLimit}
                  onChange={(event) => setDatasetLimit(Number(event.target.value) || 1)}
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-dental-textSecondary font-semibold uppercase tracking-wider">Examples Per Chunk</span>
                <input
                  className="w-full bg-dental-darkBg border border-dental-border rounded-xl py-2 px-3 text-xs text-dental-textPrimary focus:outline-none focus:border-dental-accent"
                  type="number"
                  min={1}
                  max={10}
                  value={examplesPerChunk}
                  onChange={(event) => setExamplesPerChunk(Number(event.target.value) || 1)}
                />
              </label>
            </div>

            <div className="bg-dental-darkBg/60 border border-dental-border rounded-xl p-3 grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div>
                <p className="text-dental-textSecondary">State</p>
                <p className="font-bold text-dental-textPrimary">{datasetStatus?.state || "idle"}</p>
              </div>
              <div>
                <p className="text-dental-textSecondary">Chunks</p>
                <p className="font-bold text-dental-textPrimary">{datasetStatus?.processed_chunks || 0}</p>
              </div>
              <div>
                <p className="text-dental-textSecondary">Q&A Rows</p>
                <p className="font-bold text-dental-textPrimary">{datasetStatus?.generated_items || 0}</p>
              </div>
              <div>
                <p className="text-dental-textSecondary">Skipped</p>
                <p className="font-bold text-dental-textPrimary">{datasetStatus?.skipped_chunks || 0}</p>
              </div>
              <div>
                <p className="text-dental-textSecondary">Already Done</p>
                <p className="font-bold text-dental-textPrimary">{datasetStatus?.duplicate_chunks || 0}</p>
              </div>
              <div className="md:col-span-3">
                <p className="text-dental-textSecondary">PDF</p>
                <p className="font-bold text-dental-textPrimary truncate">{datasetStatus?.document_name || "All ready PDFs"}</p>
              </div>
            </div>

            {datasetStatus?.message && (
              <p className="text-xs text-dental-textSecondary">
                {datasetStatus.message}
              </p>
            )}
          </section>

          {/* Documents Listing */}
          <section className="p-6 bg-dental-card border border-dental-border rounded-2xl space-y-4 shadow-xl max-w-4xl mx-auto">
            <h2 className="text-sm font-bold text-dental-textPrimary flex items-center gap-2">
              <Sparkles size={16} className="text-teal-400" /> Active Vector Store Indexes
            </h2>
            <div className="space-y-3">
              {documents.length ? documents.map((doc) => {
                let statusColor = "bg-amber-500/10 text-amber-400 border-amber-500/20";
                if (doc.status === "ready") {
                  statusColor = "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
                } else if (doc.status === "failed") {
                  statusColor = "bg-red-500/10 text-red-400 border-red-500/20";
                }
                const progress = Math.max(0, Math.min(doc.ingestion_progress || 0, 100));
                const logs = logsByDocument[doc.id] || [];
                const isLogsOpen = openLogDocumentId === doc.id;

                return (
                  <div className="p-4 bg-dental-darkBg border border-dental-border rounded-xl space-y-3" key={doc.id}>
                    <div className="flex flex-col md:flex-row justify-between md:items-center gap-3">
                      <div className="space-y-2 min-w-0">
                        <div className="flex items-center gap-2.5 flex-wrap">
                          <strong className="text-xs text-dental-textPrimary truncate max-w-[320px] md:max-w-[480px]">{doc.title || doc.original_filename}</strong>
                          <span className={`px-2 py-0.5 border rounded-full text-[9px] uppercase font-bold tracking-wide ${statusColor}`}>
                            {doc.status}
                          </span>
                          {doc.ocr_used && (
                            <span className="px-2 py-0.5 border rounded-full text-[9px] uppercase font-bold tracking-wide bg-sky-500/10 text-sky-300 border-sky-500/20">
                              OCR
                            </span>
                          )}
                        </div>
                        <p className="text-[10px] text-dental-textSecondary">
                          {doc.chunk_count} chunks · Uploaded: {new Date(doc.created_at).toLocaleString()}
                        </p>
                        <p className="text-[10px] text-dental-textSecondary leading-normal">
                          {doc.author_or_source || "Unknown publisher"}
                          {doc.publication_year ? ` · ${doc.publication_year}` : ""}
                          {doc.edition ? ` · ${doc.edition}` : ""}
                          {" · "}{doc.document_type.replace("_", " ")}
                          {" · "}{doc.trust_level} trust
                          {" · "}{doc.review_status} review status
                          {doc.language ? ` · ${doc.language}` : ""}
                        </p>
                      </div>
                      
                      <div className="flex gap-2 shrink-0 md:self-center">
                        <button
                          onClick={() => toggleLogs(doc.id)}
                          className="flex-1 md:flex-initial flex items-center justify-center gap-1.5 py-1.5 px-3 bg-dental-border border border-dental-border hover:bg-dental-card text-dental-textPrimary rounded-lg text-[10px] font-semibold transition-colors"
                        >
                          <ScrollText size={12} />
                          Logs
                        </button>
                        <button 
                          onClick={() => onReingest(doc.id)}
                          disabled={doc.status === "processing"}
                          className="flex-1 md:flex-initial flex items-center justify-center gap-1.5 py-1.5 px-3 bg-dental-border border border-dental-border hover:bg-dental-card text-dental-textPrimary rounded-lg text-[10px] font-semibold transition-colors disabled:opacity-40"
                        >
                          <RefreshCw size={12} />
                          Re-ingest
                        </button>
                        <button 
                          onClick={() => onDelete(doc.id)}
                          className="flex-1 md:flex-initial flex items-center justify-center gap-1.5 py-1.5 px-3 bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 rounded-lg text-[10px] font-bold transition-colors"
                        >
                          <Trash2 size={12} />
                          Delete
                        </button>
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between gap-3 text-[10px] text-dental-textSecondary">
                        <span className="truncate">{doc.ingestion_step || (doc.status === "ready" ? "Ready" : "Waiting")}</span>
                        <span className="font-semibold text-dental-textPrimary">{progress}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-dental-border overflow-hidden">
                        <div
                          className={`h-full transition-all ${doc.status === "failed" ? "bg-red-400" : "bg-dental-accent"}`}
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                    </div>

                    {doc.error_message && (
                      <p className="text-[10px] text-red-400 flex items-center gap-1.5 bg-red-500/5 p-2 rounded-lg border border-red-500/10">
                        <ShieldAlert size={12} className="shrink-0" />
                        <span>Error: {doc.error_message}</span>
                      </p>
                    )}

                    {isLogsOpen && (
                      <div className="border border-dental-border rounded-xl bg-dental-card/40 p-3 space-y-2 max-h-56 overflow-y-auto">
                        {logs.length ? logs.map((log) => {
                          const logColor = log.level === "error" ? "text-red-400" : log.level === "warning" ? "text-amber-300" : "text-dental-textSecondary";
                          return (
                            <div key={log.id} className="text-[10px] leading-relaxed">
                              <span className="text-dental-textSecondary">{new Date(log.created_at).toLocaleString()}</span>
                              <span className={`ml-2 uppercase font-bold ${logColor}`}>{log.level}</span>
                              <span className="ml-2 text-dental-textPrimary">{log.message}</span>
                            </div>
                          );
                        }) : (
                          <p className="text-[10px] text-dental-textSecondary italic">No ingestion logs yet.</p>
                        )}
                      </div>
                    )}
                  </div>
                );
              }) : (
                <p className="text-xs text-dental-textSecondary italic text-center py-6">No vector sources uploaded yet.</p>
              )}
            </div>
          </section>

          {/* Floating status bar */}
          {status && (
            <div className="fixed top-4 left-1/2 -translate-x-1/2 px-4 py-2 bg-dental-card/95 border border-dental-border rounded-full text-[10px] text-dental-textSecondary max-w-md text-center shadow-2xl z-30 pointer-events-none">
              {status}
            </div>
          )}
        </div>
      </AppShell>
    </AuthGate>
  );
}
