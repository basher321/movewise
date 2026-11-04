"use client";

import { useCallback, useEffect, useState } from "react";
import {
  listNotifications,
  resendNotification,
  type AdminUser,
  type Channel,
  type Notification,
  type NotifyStatus,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import Modal from "../Modal";
import { errorText } from "../auth/messages";
import AdminTable from "./AdminTable";
import TabPage from "./TabPage";
import { handleFailure } from "./failure";
import type { ShowToast } from "./Toast";

const CHANNEL: Record<Channel, string> = { email: "✉ Email", whatsapp: "💬 WhatsApp" };
const STATUS: Record<NotifyStatus, [string, string]> = {
  sent: ["Delivered", "bd ok"],
  sending: ["Sending", "bd warn"],
  queued: ["Queued", "bd warn"],
  failed: ["Failed", "bd no"],
};
const NOT_SET_UP = ["Email is not set up", "WhatsApp is not set up"];

type Props = { admin: AdminUser; toast: ShowToast; onSignedOut: () => void };

// The Notifications tab (aNotifs() in the reference): every email and WhatsApp message and its status.
export default function NotificationsTab({ admin, toast, onSignedOut }: Props) {
  const [channel, setChannel] = useState<Channel | "">("");
  const [status, setStatus] = useState<NotifyStatus | "">("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<Notification[] | null>(null);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [notSetUp, setNotSetUp] = useState<string[]>([]);
  const [viewing, setViewing] = useState<Notification | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const list = await listNotifications({ channel, status, q: search, page });
      setRows(list.items);
      setTotal(list.total);
      setPageSize(list.page_size);
      setNotSetUp(NOT_SET_UP.filter((e) => list.items.some((n) => n.last_error === e)));
      setError("");
    } catch (err) {
      handleFailure(err, () => setError(errorText(err)), onSignedOut);
    }
  }, [channel, status, search, page, onSignedOut]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 200);
    return () => clearTimeout(timer);
  }, [load]);

  async function resend(n: Notification) {
    try {
      await resendNotification(n.id);
      toast("Queued to send again.");
    } catch (err) {
      handleFailure(err, toast, onSignedOut);
    }
    await load();
  }

  if (error) return <div className="banner no">{error}</div>;

  return (
    <TabPage title="Notifications" sub="Every email and WhatsApp message with its delivery status.">
      {notSetUp.length ? (
        <div className="banner">
          {notSetUp.join(" and ")}, so those messages wait as “Queued”.{" "}
          {admin.role === "super_admin" ? "Set it up in Settings." : "Ask the Super Admin."}
        </div>
      ) : null}
      <div className="flt">
        <select aria-label="Channel" value={channel} onChange={(e) => (setPage(1), setChannel(e.target.value as Channel | ""))}>
          <option value="">All channels</option>
          <option value="email">Email</option>
          <option value="whatsapp">WhatsApp</option>
        </select>
        <select aria-label="Status" value={status} onChange={(e) => (setPage(1), setStatus(e.target.value as NotifyStatus | ""))}>
          <option value="">All statuses</option>
          <option value="sent">Delivered</option>
          <option value="sending">Sending</option>
          <option value="queued">Queued</option>
          <option value="failed">Failed</option>
        </select>
        <input type="search" value={search} onChange={(e) => (setPage(1), setSearch(e.target.value))} placeholder="Search name, email, phone or subject" aria-label="Search messages" />
      </div>
      <div className="card">
        {rows === null ? null : (
          <AdminTable
            rows={rows}
            rowKey={(m) => m.id}
            empty="No messages yet."
            columns={[
              { head: "Time", cell: (m) => formatDateTime(m.at) },
              { head: "Channel", cell: (m) => CHANNEL[m.channel] },
              {
                head: "To",
                cell: (m) => (
                  <>
                    <b>{m.to_name}</b>
                    <small>{m.to}</small>
                  </>
                ),
              },
              { head: "Message", cell: (m) => m.subject },
              { head: "Status", cell: (m) => <span className={STATUS[m.status][1]}>{STATUS[m.status][0]}</span> },
              {
                head: "",
                right: true,
                cell: (m) => (
                  <>
                    <button className="lk" type="button" onClick={() => setViewing(m)}>
                      View
                    </button>
                    {m.status === "failed" || m.status === "queued" ? (
                      <>
                        {" · "}
                        <button className="lk" type="button" onClick={() => void resend(m)}>
                          Resend
                        </button>
                      </>
                    ) : null}
                  </>
                ),
              },
            ]}
          />
        )}
        {total > pageSize ? (
          <div className="cr">
            <button className="btn ghost sm" type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </button>
            <span style={{ color: "var(--muted)", fontSize: 14 }}>
              Page {page} of {Math.ceil(total / pageSize)} · {total} messages
            </span>
            <button className="btn ghost sm" type="button" disabled={page * pageSize >= total} onClick={() => setPage(page + 1)}>
              Next
            </button>
          </div>
        ) : null}
      </div>
      {viewing ? (
        <Modal open title={viewing.subject || "WhatsApp message"} onClose={() => setViewing(null)}>
          <p className="sub">
            {CHANNEL[viewing.channel]} to {viewing.to} · {formatDateTime(viewing.at)} · {STATUS[viewing.status][0]}
            {viewing.tries ? " · " + viewing.tries + (viewing.tries === 1 ? " try" : " tries") : ""}
          </p>
          {viewing.last_error ? <div className="banner no">Last error: {viewing.last_error}</div> : null}
          {/* Plain text, never HTML. */}
          <pre style={{ whiteSpace: "pre-wrap", font: "15px/1.6 var(--font-dm-sans), sans-serif", margin: 0 }}>{viewing.body}</pre>
        </Modal>
      ) : null}
    </TabPage>
  );
}
