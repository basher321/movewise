"use client";

import { useCallback, useEffect, useState } from "react";
import { approveCertificate, listApplicantAccounts, listEnrolments, type ApplicantRow, type Enrolment, type EnrolmentStatus } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import { errorText } from "../auth/messages";
import { METHOD_NAMES } from "../payment/methods";
import AdminTable from "./AdminTable";
import ResetPasswordButton from "./ResetPasswordButton";
import type { ShowToast } from "./Toast";

const STATUS: Record<EnrolmentStatus, [string, string]> = {
  awaiting_payment: ["Waiting for payment", "bd warn"],
  active: ["Enrolled", "bd ok"],
  completed: ["Completed", "bd info"],
  cancelled: ["Cancelled (refunded)", "bd"],
};

// The admin Courses tab (showCourseAdm() in the reference, with the .flt search):
// one card per enrolment and "Approve certificate" for the ones not approved yet.
export default function CoursesTab({ toast }: { toast: ShowToast }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<EnrolmentStatus | "">("");
  const [rows, setRows] = useState<Enrolment[] | null>(null);
  const [total, setTotal] = useState(0);
  const [accounts, setAccounts] = useState<ApplicantRow[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async (q: string, s: EnrolmentStatus | "") => {
    try {
      const page = await listEnrolments(q, s);
      setRows(page.items);
      setTotal(page.total);
      setError("");
    } catch (err) {
      setError(errorText(err));
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void load(search, status), 200);
    return () => clearTimeout(timer);
  }, [search, status, load]);

  useEffect(() => {
    let live = true;
    void listApplicantAccounts("course")
      .then((list) => {
        if (live) setAccounts(list);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);

  async function approve(row: Enrolment) {
    try {
      await approveCertificate(row.id);
      toast("Certificate approved for " + (row.learner?.name ?? "the learner") + ".");
    } catch (err) {
      toast(errorText(err), true);
    }
    await load(search, status);
  }

  if (error) return <div className="banner no">{error}</div>;

  return (
    <>
      <div className="flt">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search name, email, course, order or certificate ID"
          aria-label="Search enrolments"
        />
        <select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value as EnrolmentStatus | "")}>
          <option value="">All enrolments</option>
          <option value="awaiting_payment">Waiting for payment</option>
          <option value="active">Enrolled</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </div>
      {rows && total > rows.length ? (
        <p className="sub">
          Showing the newest {rows.length} of {total}. Search to find others.
        </p>
      ) : null}
      {rows === null ? null : rows.length ? (
        <div className="adm-g">
          {rows.map((r) => (
            <div className="card" key={r.id}>
              <div className="top" style={{ alignItems: "center" }}>
                <h3 style={{ margin: "6px 0 4px" }}>{r.learner?.name}</h3>
                <span className={STATUS[r.status][1]}>{STATUS[r.status][0]}</span>
              </div>
              <p>{r.course.title}</p>
              <div className="kv">
                <div>
                  <span>Email</span>
                  <b>{r.learner?.email || "–"}</b>
                </div>
                <div>
                  <span>Order</span>
                  <b>{r.order_no}</b>
                </div>
                <div>
                  <span>Price</span>
                  <b>
                    {formatMoney(r.price_poisha)}
                    {r.method ? " · " + METHOD_NAMES[r.method] : ""}
                    {r.payment_status && r.payment_status !== "paid" ? " · " + r.payment_status.replace("_", " ") : ""}
                  </b>
                </div>
                <div>
                  <span>Date</span>
                  <b>{formatDate(r.enrolled_at)}</b>
                </div>
                <div>
                  <span>Certificate ID</span>
                  <b>{r.certificate_id ?? "–"}</b>
                </div>
                <div>
                  <span>Status</span>
                  <b>{r.certificate_approved ? "Certificate approved" : "Not approved yet"}</b>
                </div>
              </div>
              {r.certificate_approved || r.status !== "active" ? null : (
                <div className="cr">
                  <button className="btn sm" type="button" onClick={() => void approve(r)}>
                    Approve certificate
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p style={{ color: "var(--muted)" }}>No course enrolments yet.</p>
      )}
      <div className="card" style={{ marginTop: 24 }}>
        <h3>Learner accounts ({accounts.length})</h3>
        <AdminTable
          rows={accounts}
          rowKey={(a) => a.id}
          empty="No learner accounts yet."
          columns={[
            { head: "Account ID", cell: (a) => a.public_id },
            {
              head: "Name",
              cell: (a) => (
                <>
                  {a.name}
                  <small>{a.username ?? "signs in with email"}</small>
                </>
              ),
            },
            {
              head: "Contact",
              cell: (a) => (
                <>
                  {a.email || "–"}
                  <small>{a.phone || "–"}</small>
                </>
              ),
            },
            { head: "", right: true, cell: (a) => <ResetPasswordButton accountId={a.id} name={a.name} /> },
          ]}
        />
      </div>
    </>
  );
}
