"use client";

import { ChangeEvent, useCallback, useEffect, useState } from "react";
import { FileUp, RefreshCw, Trash2 } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { deleteDocument, getDocuments, reingestDocument, uploadDocument } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DocumentItem } from "@/lib/types";

export default function AdminPage() {
  const { token } = useAuth();
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
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

  const loadDocuments = useCallback(async () => {
    if (!token) return;
    try {
      setDocuments(await getDocuments(token));
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not load documents");
    }
  }, [token]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

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
      setStatus(error instanceof Error ? error.message : "Upload failed");
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
      setStatus(error instanceof Error ? error.message : "Re-ingest failed");
    }
  }

  function pollDocuments() {
    let attempts = 0;
    const timer = window.setInterval(async () => {
      attempts += 1;
      await loadDocuments();
      if (attempts >= 20) {
        window.clearInterval(timer);
        setStatus("Refresh documents to check final ingestion status.");
      }
    }, 3000);
  }

  async function onDelete(documentId: string) {
    if (!token) return;
    setStatus("Deleting document...");
    try {
      await deleteDocument(documentId, token);
      await loadDocuments();
      setStatus("Document deleted.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Delete failed");
    }
  }

  return (
    <AuthGate adminOnly>
      <AppShell title="Admin Workspace" subtitle="Upload, re-ingest, and manage dental knowledge PDFs.">
        <div className="content grid">
          <section className="panel grid">
            <h2>Upload Dental PDF</h2>
            <div className="notice">
              Add source metadata first. The parser then extracts page-aware text, cleans it, chunks it, embeds it, and stores citation payloads in Qdrant.
            </div>
            <div className="grid two">
              <label className="field">
                <span>Book title</span>
                <input className="input" value={bookTitle} onChange={(event) => setBookTitle(event.target.value)} placeholder="Dental Caries Textbook" />
              </label>
              <label className="field">
                <span>Author or source</span>
                <input className="input" value={authorOrSource} onChange={(event) => setAuthorOrSource(event.target.value)} placeholder="WHO / Author name" />
              </label>
              <label className="field">
                <span>Year</span>
                <input className="input" type="number" value={year} onChange={(event) => setYear(event.target.value)} placeholder="2022" min="1800" max="2100" />
              </label>
              <label className="field">
                <span>Edition</span>
                <input className="input" value={edition} onChange={(event) => setEdition(event.target.value)} placeholder="3rd edition" />
              </label>
              <label className="field">
                <span>Document type</span>
                <select className="input" value={documentType} onChange={(event) => setDocumentType(event.target.value)}>
                  <option value="textbook">Textbook</option>
                  <option value="guideline">Guideline</option>
                  <option value="patient_education">Patient education</option>
                  <option value="research_article">Research article</option>
                  <option value="other">Other</option>
                </select>
              </label>
              <label className="field">
                <span>Trust level</span>
                <select className="input" value={trustLevel} onChange={(event) => setTrustLevel(event.target.value)}>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
              </label>
              <label className="field">
                <span>Specialty</span>
                <input className="input" value={specialty} onChange={(event) => setSpecialty(event.target.value)} placeholder="Oral medicine" />
              </label>
              <label className="field">
                <span>Language</span>
                <input className="input" value={language} onChange={(event) => setLanguage(event.target.value)} placeholder="English" />
              </label>
              <label className="field">
                <span>Review status</span>
                <select className="input" value={reviewStatus} onChange={(event) => setReviewStatus(event.target.value)}>
                  <option value="unreviewed">Unreviewed</option>
                  <option value="reviewed">Reviewed</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                </select>
              </label>
            </div>
            <div className="inline-actions">
              <input
                className="input"
                type="file"
                accept="application/pdf"
                onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] || null)}
              />
              <button className="button" onClick={onUpload} disabled={!file || isUploading}>
                <FileUp size={17} />
                {isUploading ? "Working..." : "Upload"}
              </button>
              <button className="button secondary" onClick={loadDocuments}>
                <RefreshCw size={17} />
                Refresh
              </button>
            </div>
            <p className="status">{status}</p>
          </section>

          <section className="panel">
            <h2>Documents</h2>
            <div className="list">
              {documents.length ? documents.map((document) => (
                <div className="list-item" key={document.id}>
                  <div className="inline-actions" style={{ justifyContent: "space-between" }}>
                    <div>
                      <strong>{document.title || document.original_filename}</strong>
                      <p className="muted">
                        {document.status} · {document.chunk_count} chunks · {new Date(document.created_at).toLocaleString()}
                      </p>
                      <p className="muted">
                        {document.author_or_source || "Unknown source"}
                        {document.publication_year ? ` · ${document.publication_year}` : ""}
                        {document.edition ? ` · ${document.edition}` : ""}
                        {" · "}{document.document_type.replace("_", " ")}
                        {" · "}{document.trust_level} trust
                        {" · "}{document.review_status}
                        {document.language ? ` · ${document.language}` : ""}
                      </p>
                    </div>
                    <span className="badge">{document.status}</span>
                  </div>
                  {document.error_message ? <p className="muted">{document.error_message}</p> : null}
                  <div className="inline-actions">
                    <button className="button secondary" onClick={() => onReingest(document.id)}>
                      <RefreshCw size={16} />
                      Re-ingest
                    </button>
                    <button className="button danger" onClick={() => onDelete(document.id)}>
                      <Trash2 size={16} />
                      Delete
                    </button>
                  </div>
                </div>
              )) : <p className="muted">No documents uploaded yet.</p>}
            </div>
          </section>
        </div>
      </AppShell>
    </AuthGate>
  );
}
