"use client";

import { useCallback, useEffect, useState } from "react";
import { listDocuments, type AppStatus, type DocFilter, type DocumentRow, type ShownDocStatus } from "@/lib/api";
import { formatDate } from "@/lib/format";
import DocumentViewer from "../agent/DocumentViewer";
import { errorText } from "../auth/messages";
import { RejectDocDialog, VerifyDocDialog } from "./DocReviewDialogs";
import TabPage from "./TabPage";
import { handleFailure } from "./failure";
import type { ShowToast } from "./Toast";

type Filter = DocFilter;

const FILTERS: [Filter, string][] = [
  ["pending", "Waiting review"],
  ["expiring", "Expiring in 60 days"],
  ["expired", "Expired"],
  ["rejected", "Rejected"],
  ["verified", "Verified"],
  ["all", "All"],
];

// DST and STS in the reference.
const DOC_STATUS: Record<ShownDocStatus, [string, string]> = {
  pending: ["Waiting review", "bd warn"],
  verified: ["Verified", "bd ok"],
  rejected: ["Rejected", "bd no"],
  expiring: ["Expiring soon", "bd warn"],
  expired: ["Expired", "bd no"],
  replaced: ["Replaced", "bd"],
};

const APP_STATUS: Record<AppStatus, string> = {
  active: "Active",
  on_hold: "On hold",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  completed: "Completed",
};

type Props = { toast: ShowToast; onSignedOut: () => void };

// The Documents tab (aDocs() in the reference): uploads of the modules this admin may open.
export default function DocumentsTab({ toast, onSignedOut }: Props) {
  const [filter, setFilter] = useState<Filter>("pending");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<DocumentRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [error, setError] = useState("");
  const [viewing, setViewing] = useState<DocumentRow | null>(null);
  const [review, setReview] = useState<{ doc: DocumentRow; kind: "verify" | "reject" } | null>(null);

  const load = useCallback(async () => {
    try {
      const list = await listDocuments(filter, search, page);
      setRows(list.items);
      setTotal(list.total);
      setPageSize(list.page_size);
      setError("");
    } catch (err) {
      handleFailure(err, () => setError(errorText(err)), onSignedOut);
    }
  }, [filter, search, page, onSignedOut]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 200);
    return () => clearTimeout(timer);
  }, [load]);

  if (error) return <div className="banner no">{error}</div>;

  function done(message: string) {
    setReview(null);
    toast(message);
    void load();
  }

  return (
    <TabPage title="Documents" sub="Review uploads, set expiry dates and see what is about to expire.">
      <div className="flt">
        <select aria-label="Show" value={filter} onChange={(e) => (setPage(1), setFilter(e.target.value as Filter))}>
          {FILTERS.map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
        <input
          type="search"
          value={search}
          onChange={(e) => (setPage(1), setSearch(e.target.value))}
          placeholder="Search name, email, reference or document"
          aria-label="Search documents"
        />
      </div>
      <div className="card">
        {rows === null ? null : rows.length ? (
          rows.map((d) => {
            const [label, cls] = DOC_STATUS[d.shown_status];
            return (
              <div key={d.id}>
                <small style={{ color: "var(--muted)", fontSize: 13, display: "block", marginTop: 10 }}>
                  {d.applicant.name} · {d.applicant.email || "no email"} · {d.application_ref} ({APP_STATUS[d.application_status]}) · {d.item_title}
                </small>
                <div className="xrow">
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <b>{d.type}</b>
                    <small>
                      {d.original_name} · {Math.max(1, Math.round(d.size_bytes / 1024))} KB · {formatDate(d.uploaded_at)}
                      {d.expiry ? " · expires " + d.expiry : ""}
                      {d.note ? " · " + d.note : ""}
                    </small>
                  </div>
                  <div className="cr" style={{ margin: 0, gap: 8 }}>
                    <span className={cls}>{label}</span>
                    <button type="button" className="lk" onClick={() => setViewing(d)}>
                      View
                    </button>
                    {d.status === "pending" ? (
                      <>
                        <button type="button" className="btn sm" onClick={() => setReview({ doc: d, kind: "verify" })}>
                          Verify
                        </button>
                        <button type="button" className="btn ghost sm" onClick={() => setReview({ doc: d, kind: "reject" })}>
                          Reject
                        </button>
                      </>
                    ) : null}
                  </div>
                </div>
              </div>
            );
          })
        ) : (
          <p style={{ color: "var(--muted)", margin: 0 }}>Nothing in this list.</p>
        )}
        {total > pageSize ? (
          <div className="cr">
            <button className="btn ghost sm" type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </button>
            <span style={{ color: "var(--muted)", fontSize: 14 }}>
              Page {page} of {Math.ceil(total / pageSize)} · {total} documents
            </span>
            <button className="btn ghost sm" type="button" disabled={page * pageSize >= total} onClick={() => setPage(page + 1)}>
              Next
            </button>
          </div>
        ) : null}
      </div>
      {viewing ? <DocumentViewer doc={viewing} onClose={() => setViewing(null)} /> : null}
      {review?.kind === "verify" ? (
        <VerifyDocDialog doc={review.doc} onClose={() => setReview(null)} onDone={() => done("Document verified.")} onSignedOut={onSignedOut} />
      ) : null}
      {review?.kind === "reject" ? (
        <RejectDocDialog doc={review.doc} onClose={() => setReview(null)} onDone={() => done("Document rejected.")} onSignedOut={onSignedOut} />
      ) : null}
    </TabPage>
  );
}
