"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  archivePartyDocument,
  isApiError,
  listPartyDocuments,
  MAX_PARTY_DOCUMENT_BYTES,
  PARTY_DOC_TYPES,
  uploadPartyDocument,
  type DocumentOwnerKind,
  type PartyDocShownStatus,
  type PartyDocType,
  type PartyDocument,
} from "@/lib/api";
import { formatDate } from "@/lib/format";
import Modal from "../Modal";
import { errorText } from "../auth/messages";

export const PARTY_DOC_TYPE_LABELS: Record<PartyDocType, string> = {
  agreement: "Agreement",
  trade_licence: "Trade licence",
  id_document: "ID document",
  bank_details: "Bank details",
  other: "Other",
};

const STATUS_BADGE: Record<PartyDocShownStatus, [string, string]> = {
  active: ["bd ok", "Active"],
  expiring: ["bd warn", "Expiring soon"],
  expired: ["bd no", "Expired"],
  archived: ["bd", "Archived"],
};

const ACCEPT = "application/pdf,image/jpeg,image/png";

function sizeText(bytes: number): string {
  return bytes >= 1024 * 1024 ? (bytes / (1024 * 1024)).toFixed(1) + " MB" : Math.max(1, Math.round(bytes / 1024)) + " KB";
}

type Props = {
  kind: DocumentOwnerKind;
  ownerId: string;
  ownerName: string;
  // Upload and archive: the super admin for agents; the super admin and section admins for partners.
  canEdit: boolean;
  onClose: () => void;
  onSignedOut: () => void;
  onChanged?: (message: string) => void;
};

// Agreements and other documents of an agent or partner (B21). Not in the reference: it follows
// the admin dialog style (Modal, .fgrid / .fl fields, .xrow list rows, .bd badges).
export default function PartyDocumentsDialog({ kind, ownerId, ownerName, canEdit, onClose, onSignedOut, onChanged }: Props) {
  const [docs, setDocs] = useState<PartyDocument[] | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // The upload form.
  const [docType, setDocType] = useState<PartyDocType>("agreement");
  const [title, setTitle] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);

  const fail = useCallback(
    (err: unknown) => {
      if (isApiError(err) && err.code === "UNAUTHENTICATED") return onSignedOut();
      setError(errorText(err));
    },
    [onSignedOut],
  );

  const load = useCallback(async () => {
    try {
      setDocs(await listPartyDocuments(kind, ownerId));
    } catch (err) {
      fail(err);
    }
  }, [kind, ownerId, fail]);

  useEffect(() => {
    let alive = true;
    listPartyDocuments(kind, ownerId)
      .then((list) => {
        if (alive) setDocs(list);
      })
      .catch((err: unknown) => {
        if (alive) fail(err);
      });
    return () => {
      alive = false;
    };
  }, [kind, ownerId, fail]);

  async function upload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setError("");
    if (!file) return setError("Please choose a file.");
    if (file.size > MAX_PARTY_DOCUMENT_BYTES) return setError("The file must be 10 MB or smaller.");
    setBusy(true);
    try {
      await uploadPartyDocument(kind, ownerId, { doc_type: docType, title: title.trim(), valid_until: validUntil || null, note: note.trim(), file });
      setTitle("");
      setValidUntil("");
      setNote("");
      setFile(null);
      setFileKey((k) => k + 1);
      await load();
      onChanged?.("Document uploaded.");
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function archive(doc: PartyDocument) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await archivePartyDocument(kind, ownerId, doc.id);
      setConfirming(null);
      await load();
      onChanged?.("Document archived.");
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  const current = docs?.filter((d) => d.status === "active") ?? [];
  const archived = docs?.filter((d) => d.status === "archived") ?? [];
  const shown = showArchived ? [...current, ...archived] : current;

  return (
    <Modal open wide title={"Documents of " + ownerName} onClose={onClose}>
      <p className="sub">Agreements, licences and other papers of this {kind}. Only staff can see them. Old documents are archived, never deleted.</p>

      {docs === null ? null : shown.length === 0 ? (
        <p style={{ color: "var(--muted)", margin: "0 0 14px" }}>{current.length === 0 && archived.length > 0 ? "No current documents." : "No documents yet."}</p>
      ) : (
        <div style={{ marginBottom: 14 }}>
          {shown.map((d) => {
            const [badge, badgeText] = STATUS_BADGE[d.shown_status];
            return (
              <div className="xrow" key={d.id}>
                <div style={{ minWidth: 0, flex: "1 1 240px" }}>
                  <b style={{ overflowWrap: "anywhere" }}>
                    {PARTY_DOC_TYPE_LABELS[d.doc_type]}
                    {d.title ? ": " + d.title : ""}
                  </b>
                  <small style={{ overflowWrap: "anywhere" }}>
                    {d.original_name} · {sizeText(d.size_bytes)}
                  </small>
                  <small>
                    Uploaded {formatDate(d.uploaded_at)} by {d.uploaded_by_name}
                    {d.valid_until ? " · Valid until " + formatDate(d.valid_until) : ""}
                  </small>
                  {d.archived_at ? (
                    <small>
                      Archived {formatDate(d.archived_at)}
                      {d.archived_by_name ? " by " + d.archived_by_name : ""}
                    </small>
                  ) : null}
                  {d.note ? <small style={{ overflowWrap: "anywhere" }}>{d.note}</small> : null}
                </div>
                <span className="cr" style={{ margin: 0 }}>
                  <span className={badge} style={{ margin: 0 }}>
                    {badgeText}
                  </span>
                  <a className="lk" href={d.file_url} target="_blank" rel="noopener noreferrer">
                    Open ↗
                  </a>
                  {canEdit && d.status === "active" ? (
                    confirming === d.id ? (
                      <>
                        <button className="lk r" type="button" disabled={busy} onClick={() => void archive(d)}>
                          Yes, archive
                        </button>
                        <button className="lk" type="button" onClick={() => setConfirming(null)}>
                          Keep
                        </button>
                      </>
                    ) : (
                      <button className="lk r" type="button" onClick={() => setConfirming(d.id)}>
                        Archive
                      </button>
                    )
                  ) : null}
                </span>
              </div>
            );
          })}
        </div>
      )}
      {archived.length > 0 ? (
        <p style={{ margin: "0 0 14px" }}>
          <button className="lk" type="button" onClick={() => setShowArchived((v) => !v)}>
            {showArchived ? "Hide archived" : `Show archived (${archived.length})`}
          </button>
        </p>
      ) : null}

      {canEdit ? (
        <form noValidate onSubmit={upload} style={{ borderTop: "1px solid var(--line)", paddingTop: 16, gap: 0 }}>
          <h4 style={{ margin: "0 0 12px" }}>Upload a document</h4>
          <div className="fgrid">
            <label className="fl">
              <span>Type</span>
              <select value={docType} onChange={(e) => setDocType(e.target.value as PartyDocType)}>
                {PARTY_DOC_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {PARTY_DOC_TYPE_LABELS[t]}
                  </option>
                ))}
              </select>
            </label>
            <label className="fl">
              <span>Title (optional)</span>
              <input value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Signed agreement 2026" />
            </label>
            <label className="fl">
              <span>Valid until (optional)</span>
              <input type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />
            </label>
            <label className="fl">
              <span>File (PDF, JPG or PNG, up to 10 MB)</span>
              <input key={fileKey} type="file" accept={ACCEPT} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </label>
            <label className="fl" style={{ gridColumn: "1/-1" }}>
              <span>Note (optional, only staff see it)</span>
              <input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Original kept in office file 12" />
            </label>
          </div>
          <p className="err" role="alert">
            {error}
          </p>
          <div className="cr" style={{ margin: 0 }}>
            <button className="btn sm" type="submit" disabled={busy}>
              {busy ? "Uploading…" : "Upload"}
            </button>
            <button className="btn ghost sm" type="button" onClick={onClose}>
              Close
            </button>
          </div>
        </form>
      ) : (
        <>
          <p className="err" role="alert">
            {error}
          </p>
          <div className="cr" style={{ margin: 0 }}>
            <button className="btn ghost sm" type="button" onClick={onClose}>
              Close
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}
