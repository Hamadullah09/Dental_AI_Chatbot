"use client";

import { ChangeEvent, useEffect, useState } from "react";
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
  const [status, setStatus] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  async function loadDocuments() {
    if (!token) return;
    try {
      setDocuments(await getDocuments(token));
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not load documents");
    }
  }

  useEffect(() => {
    loadDocuments();
  }, [token]);

  async function onUpload() {
    if (!token || !file) return;
    setIsUploading(true);
    setStatus("Uploading and ingesting PDF...");
    try {
      await uploadDocument(file, token);
      setFile(null);
      setStatus("Document uploaded and ingested.");
      await loadDocuments();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setIsUploading(false);
    }
  }

  async function onReingest(documentId: string) {
    if (!token) return;
    setStatus("Re-ingesting document...");
    try {
      await reingestDocument(documentId, token);
      await loadDocuments();
      setStatus("Document re-ingested.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Re-ingest failed");
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
              Uploaded PDFs are parsed into page-aware chunks, embedded, stored in Qdrant, and tracked in the application database.
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
                      <strong>{document.original_filename}</strong>
                      <p className="muted">
                        {document.status} · {document.chunk_count} chunks · {new Date(document.created_at).toLocaleString()}
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
