"use client";

import { useCallback, useEffect, useState } from "react";
import { ADMIN_ROLES, AUDIT_ROWS_PER_PAGE as ROWS_PER_PAGE, listAudit, type AdminRole, type AuditPage } from "@/lib/api";
import { ROLE_NAMES } from "@/lib/admin/tabs";
import { formatDateTime } from "@/lib/format";
import { errorText } from "../auth/messages";
import AdminTable from "./AdminTable";
import TabPage from "./TabPage";
import { handleFailure } from "./failure";

function roleName(role: string | null): string {
  if (!role) return "System";
  return (ADMIN_ROLES as readonly string[]).includes(role) ? ROLE_NAMES[role as AdminRole] : role;
}

// The Audit log tab (aAudit() in the reference): read-only, 50 rows per page, newest first.
export default function AuditTab({ onSignedOut }: { onSignedOut: () => void }) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<AuditPage | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await listAudit(search, page));
      setError("");
    } catch (err) {
      handleFailure(err, () => setError(errorText(err)), onSignedOut);
    }
  }, [search, page, onSignedOut]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) return <div className="banner no">{error}</div>;

  const pages = data ? Math.max(1, Math.ceil(data.total / ROWS_PER_PAGE)) : 1;

  return (
    <TabPage title="Audit log" sub="Who did what and when. Entries cannot be edited.">
      <div className="flt">
        <input
          type="search"
          defaultValue={search}
          placeholder="Search person, action or detail"
          aria-label="Search the audit log"
          // As in the reference, the search runs on change: Enter or leaving the box.
          onBlur={(e) => {
            setPage(1);
            setSearch(e.target.value);
          }}
          onKeyDown={(e) => {
            if (e.key !== "Enter") return;
            setPage(1);
            setSearch(e.currentTarget.value);
          }}
        />
      </div>
      <div className="card">
        {data === null ? null : (
          <AdminTable
            rows={data.rows}
            rowKey={(a) => a.id}
            empty={search.trim() ? "No activity matches." : "No activity yet."}
            columns={[
              { head: "Time", cell: (a) => formatDateTime(a.at) },
              {
                head: "By",
                cell: (a) => (
                  <>
                    <b>{a.by_name}</b>
                    <small>{roleName(a.by_role)}</small>
                  </>
                ),
              },
              { head: "Action", cell: (a) => a.action },
              { head: "Detail", cell: (a) => <span style={{ fontSize: 14 }}>{a.detail}</span> },
            ]}
          />
        )}
        {data && data.total > ROWS_PER_PAGE ? (
          <div className="cr">
            <button className="btn ghost sm" type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </button>
            <span style={{ color: "var(--muted)", fontSize: 14 }}>
              Page {page} of {pages} · {data.total} entries
            </span>
            <button className="btn ghost sm" type="button" disabled={page >= pages} onClick={() => setPage(page + 1)}>
              Next
            </button>
          </div>
        ) : null}
      </div>
    </TabPage>
  );
}
