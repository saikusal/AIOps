import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { deleteDocument, fetchDocuments, uploadDocument } from "../lib/api";
import { useRefreshQueryOptions } from "../lib/refresh";

export function DocumentsPage() {
  const queryClient = useQueryClient();
  const refreshQueryOptions = useRefreshQueryOptions();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const documentsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: fetchDocuments,
    ...refreshQueryOptions,
  });

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!selectedFile) {
        throw new Error("Choose a file before uploading.");
      }
      await uploadDocument(selectedFile);
    },
    onSuccess: async () => {
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDocument,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  return (
    <>
      <section className="hero-card hero-card--documents">
        <div className="eyebrow">Documents</div>
        <h2>Knowledge Base</h2>
        <p>
          Keep operational runbooks, troubleshooting notes, and product documentation available to the assistant without leaving the platform.
        </p>
      </section>

      <section className="documents-layout">
        <article className="page-card documents-upload-card">
          <div className="eyebrow">Upload</div>
          <h2>Add New Knowledge</h2>
          <p>Upload operational runbooks, product docs, or troubleshooting notes for the assistant to use when documents are requested.</p>
          <div className="documents-upload-form">
            <input
              ref={fileInputRef}
              type="file"
              onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
            />
            <button
              className="assistant-button"
              disabled={!selectedFile || uploadMutation.isPending}
              onClick={() => uploadMutation.mutate()}
            >
              {uploadMutation.isPending ? "Uploading..." : "Upload Document"}
            </button>
          </div>
          {selectedFile ? <div className="documents-upload-meta">Selected: {selectedFile.name}</div> : null}
          {uploadMutation.isError ? (
            <div className="documents-upload-error">
              {(uploadMutation.error as Error)?.message || "Upload failed."}
            </div>
          ) : null}
        </article>

        <article className="page-card documents-list-card">
          <div className="documents-list-card__header">
            <div>
              <div className="eyebrow">Library</div>
              <h2>Uploaded Documents</h2>
            </div>
            <button className="assistant-button assistant-button--secondary" onClick={() => documentsQuery.refetch()}>
              Refresh
            </button>
          </div>

          {documentsQuery.isLoading ? (
            <p>Loading document inventory…</p>
          ) : (
            <div className="documents-table">
              {(documentsQuery.data || []).map((document) => (
                <article key={document.id} className="document-row">
                  <div className="document-row__meta">
                    <a href={document.fileUrl} target="_blank" rel="noreferrer">
                      {document.fileName}
                    </a>
                    <span
                      className={`app-portfolio__status app-portfolio__status--${
                        document.status === "success"
                          ? "healthy"
                          : document.status === "failed"
                            ? "down"
                            : "degraded"
                      }`}
                    >
                      {document.statusLabel}
                    </span>
                  </div>
                  <button
                    className="assistant-button assistant-button--danger"
                    disabled={deleteMutation.isPending}
                    onClick={() => deleteMutation.mutate(document.deletePath)}
                  >
                    Delete
                  </button>
                </article>
              ))}
              {!documentsQuery.data?.length ? <p>No documents uploaded yet.</p> : null}
            </div>
          )}
        </article>
      </section>
    </>
  );
}
