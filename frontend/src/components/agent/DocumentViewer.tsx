"use client";

import type { AppDocument } from "@/lib/api";
import Modal from "../Modal";

// Shows an uploaded document (the "View" dialog of bindDocs() in the reference). The file comes
// from the backend, which checks who may open it. Pictures show here; a PDF opens in a new tab.
export default function DocumentViewer({ doc, onClose }: { doc: AppDocument; onClose: () => void }) {
  const isImage = doc.mime === "image/png" || doc.mime === "image/jpeg";
  return (
    <Modal open title={doc.type} onClose={onClose}>
      {isImage ? (
        // eslint-disable-next-line @next/next/no-img-element -- a private file served by the backend
        <img src={doc.file_url} alt={doc.type} style={{ maxWidth: "100%", borderRadius: 10 }} />
      ) : (
        <p style={{ margin: 0 }}>This document is a PDF. Open it in a new tab or download it.</p>
      )}
      <p className="sub" style={{ marginTop: 10 }}>
        {doc.original_name} · {Math.max(1, Math.round(doc.size_bytes / 1024))} KB
      </p>
      <div className="cr" style={{ margin: 0 }}>
        <a className="btn sm" href={doc.file_url} target="_blank" rel="noopener noreferrer">
          Open in a new tab ↗
        </a>
        <a className="btn ghost sm" href={doc.file_url} download={doc.original_name}>
          Download
        </a>
      </div>
    </Modal>
  );
}
