"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  addInternalNote,
  APP_STATUSES,
  caseLetterPdfUrl,
  changeStage,
  changeStatus,
  COUNTRY_FLAGS,
  INTERVIEW_RESULTS,
  isApiError,
  issueCaseLetter,
  listApplicantAccounts,
  listApplications,
  listAssignableAdmins,
  listInvoices,
  resendNotification,
  sendCaseEmail,
  sendCaseLetter,
  setCaseFee,
  updateCase,
  type AdminUser,
  type AppDocument,
  type AppModule,
  type AppStatus,
  type ApplicantRow,
  type CaseChanges,
  type CaseRow,
  type Channel,
  type Invoice,
  type InterviewResult,
  type ShownDocStatus,
  type StaffMember,
} from "@/lib/api";
import { formatDate, formatDateTime, formatMoney } from "@/lib/format";
import DocumentViewer from "../agent/DocumentViewer";
import { configOf } from "../modules";
import Modal from "../Modal";
import { useSettings } from "../SettingsProvider";
import { errorText } from "../auth/messages";
import InvoiceDialog from "../payment/InvoiceDialog";
import AdminTable from "./AdminTable";
import CaseAgentDialog from "./CaseAgentDialog";
import { ChannelPicker, GroupMessageDialog, MessageDialog, SendDocumentDialog } from "./ClientMessaging";
import { RejectDocDialog, VerifyDocDialog } from "./DocReviewDialogs";
import { TextField } from "./Field";
import TabPage from "./TabPage";
import ResetPasswordButton from "./ResetPasswordButton";
import { handleFailure } from "./failure";
import type { ShowToast } from "./Toast";

const STATUS: Record<AppStatus, [string, string]> = {
  active: ["Active", "bd ok"],
  on_hold: ["On hold", "bd warn"],
  rejected: ["Rejected", "bd no"],
  withdrawn: ["Withdrawn", "bd"],
  completed: ["Completed", "bd info"],
};
const DOC_STATUS: Record<ShownDocStatus, [string, string]> = {
  pending: ["Waiting review", "bd warn"],
  verified: ["Verified", "bd ok"],
  rejected: ["Rejected", "bd no"],
  expiring: ["Expiring soon", "bd warn"],
  expired: ["Expired", "bd no"],
  replaced: ["Replaced", "bd"],
};
const RESULT: Record<InterviewResult, string> = { pending: "Pending", passed: "Passed", failed: "Failed" };

// Per module: the words of the reference tabs.
const WORDS: Record<AppModule, { title: string; who: string; provider: string; badge: string; emailApplicant: string; emailProvider: string }> = {
  study: {
    title: "Student Consultancy",
    who: "Student",
    provider: "university",
    badge: "Student",
    emailApplicant: "✉ Message applicant",
    emailProvider: "✉ Email university",
  },
  job: { title: "Job Processing", who: "Job holder", provider: "employer", badge: "Job", emailApplicant: "✉ Message job holder", emailProvider: "✉ Email employer" },
  visa: {
    title: "Immigration Processing",
    who: "Applicant",
    provider: "embassy",
    badge: "Visa",
    emailApplicant: "✉ Message applicant",
    emailProvider: "✉ Email embassy",
  },
  remote: {
    title: "Remote Jobs",
    who: "Remote worker",
    provider: "employer",
    badge: "Remote",
    emailApplicant: "✉ Message applicant",
    emailProvider: "✉ Email employer",
  },
};

type Props = { module: AppModule; admin: AdminUser; toast: ShowToast; onSignedOut: () => void };

// The Student Consultancy, Job Processing and Immigration Processing admin tabs (spec F08, B19): every application of the module.
export default function CasesTab({ module, admin, toast, onSignedOut }: Props) {
  const words = WORDS[module];
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<AppStatus | "">("active");
  const [assigned, setAssigned] = useState("");
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<CaseRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [accounts, setAccounts] = useState<ApplicantRow[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [shownInvoice, setShownInvoice] = useState<Invoice | null>(null);
  const [messageTo, setMessageTo] = useState<ApplicantRow | null>(null);
  const [groupOpen, setGroupOpen] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [list, people] = await Promise.all([listApplications(module, { q, status, assigned, page }), listAssignableAdmins(module)]);
      setRows(list.items);
      setTotal(list.total);
      setPageSize(list.page_size);
      setStaff(people);
      setError("");
    } catch (err) {
      handleFailure(err, () => setError(errorText(err)), onSignedOut);
    }
  }, [module, q, status, assigned, page, onSignedOut]);

  const loadTables = useCallback(async () => {
    try {
      const [a, i] = await Promise.all([listApplicantAccounts(module), listInvoices("", module)]);
      setAccounts(a);
      setInvoices(i.items);
    } catch {
      // The tables below the cards are optional; the cards still work.
    }
  }, [module]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 200);
    return () => clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    void loadTables();
  }, [loadTables]);

  if (error) return <div className="banner no">{error}</div>;

  const paidCount = rows?.filter((r) => r.fee_paid).length ?? 0;
  const fail = (err: unknown) => handleFailure(err, toast, onSignedOut);
  const reload = () => void load();

  return (
    <TabPage
      title={words.title}
      sub="Every application: stage, status, documents, history and emails."
      actions={
        <button className="btn ghost sm" type="button" onClick={() => setGroupOpen(true)}>
          ✉ Message a group
        </button>
      }
    >
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", marginBottom: 18 }}>
        <div className="card">
          <p>Applications{status ? " (" + STATUS[status][0].toLowerCase() + ")" : ""}</p>
          <h3 style={{ margin: "6px 0 0" }}>{total}</h3>
        </div>
        <div className="card">
          <p>Fee paid · on this page</p>
          <h3 style={{ margin: "6px 0 0" }}>{paidCount}</h3>
        </div>
      </div>
      <div className="flt">
        <input
          type="search"
          value={q}
          onChange={(e) => (setPage(1), setQ(e.target.value))}
          placeholder={"Search name, email, " + (module === "study" ? "university" : module === "visa" ? "visa programme" : "job or employer") + " or ref"}
          aria-label="Search applications"
        />
        <select aria-label="Status" value={status} onChange={(e) => (setPage(1), setStatus(e.target.value as AppStatus | ""))}>
          <option value="">All statuses</option>
          {APP_STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS[s][0]}
            </option>
          ))}
        </select>
        <select aria-label="Assigned to" value={assigned} onChange={(e) => (setPage(1), setAssigned(e.target.value))}>
          <option value="">Anyone</option>
          <option value="me">Assigned to me</option>
          <option value="none">Unassigned</option>
        </select>
      </div>
      {rows === null ? null : rows.length ? (
        rows.map((r) => <CaseCard key={r.id + r.updated_at} row={r} module={module} admin={admin} staff={staff} toast={toast} onChanged={reload} onFail={fail} onSignedOut={onSignedOut} />)
      ) : (
        <div className="card">
          <p style={{ margin: 0, color: "var(--muted)" }}>No applications here yet.</p>
        </div>
      )}
      {total > pageSize ? (
        <div className="cr">
          <button className="btn ghost sm" type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <span style={{ color: "var(--muted)", fontSize: 14 }}>
            Page {page} of {Math.ceil(total / pageSize)}
          </span>
          <button className="btn ghost sm" type="button" disabled={page * pageSize >= total} onClick={() => setPage(page + 1)}>
            Next
          </button>
        </div>
      ) : null}

      <div className="card" style={{ marginTop: 24 }}>
        <h3>
          {words.title} accounts ({accounts.length})
        </h3>
        <AdminTable
          rows={accounts}
          rowKey={(a) => a.id}
          empty="No accounts yet."
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
            { head: "Joined", cell: (a) => formatDate(a.created_at) },
            {
              head: "",
              right: true,
              cell: (a) => (
                <>
                  <button className="lk" type="button" onClick={() => setMessageTo(a)}>
                    Send message
                  </button>{" "}
                  <ResetPasswordButton accountId={a.id} name={a.name} />
                </>
              ),
            },
          ]}
        />
      </div>
      <div className="card" style={{ marginTop: 18 }}>
        <h3>Invoices &amp; confirmation emails ({invoices.length})</h3>
        <AdminTable
          rows={invoices}
          rowKey={(i) => i.no}
          empty="No invoices yet."
          columns={[
            { head: "Invoice", cell: (i) => i.no },
            {
              head: "Customer",
              cell: (i) => (
                <>
                  {i.name}
                  <small>{i.email}</small>
                </>
              ),
            },
            { head: "Email", cell: (i) => (i.email_status === "sent" ? "Sent" : i.email_status === "failed" ? "Failed" : "Queued") },
            { head: "Amount", cell: (i) => formatMoney(i.amount_poisha) + (i.status === "refunded" ? " (refunded)" : "") },
            {
              head: "",
              right: true,
              cell: (i) => (
                <button className="lk" type="button" onClick={() => setShownInvoice(i)}>
                  View
                </button>
              ),
            },
          ]}
        />
      </div>
      <InvoiceDialog invoice={shownInvoice} open={shownInvoice !== null} onClose={() => setShownInvoice(null)} />
      {messageTo ? (
        <MessageDialog
          accountId={messageTo.id}
          name={messageTo.name}
          email={messageTo.email}
          phone={messageTo.phone || null}
          onClose={() => setMessageTo(null)}
          onDone={(n) => {
            setMessageTo(null);
            toast(n + (n === 1 ? " message" : " messages") + " queued.");
          }}
          onSignedOut={onSignedOut}
        />
      ) : null}
      {groupOpen ? (
        <GroupMessageDialog
          module={module}
          onClose={() => setGroupOpen(false)}
          onDone={(people, n) => {
            setGroupOpen(false);
            toast(n + " messages queued for " + people + (people === 1 ? " client." : " clients."));
          }}
          onSignedOut={onSignedOut}
        />
      ) : null}
    </TabPage>
  );
}

type CardProps = {
  row: CaseRow;
  module: AppModule;
  admin: AdminUser;
  staff: StaffMember[];
  toast: ShowToast;
  onChanged: () => void;
  onFail: (err: unknown) => void;
  onSignedOut: () => void;
};

// datetime-local value in Dhaka time from an ISO time with the Dhaka offset (the backend sends +06:00).
function localInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const dhaka = new Date(d.getTime() + 6 * 3600 * 1000);
  return dhaka.toISOString().slice(0, 16);
}

function CaseCard({ row: r, module, admin, staff, toast, onChanged, onFail, onSignedOut }: CardProps) {
  const words = WORDS[module];
  // Remote Jobs cases are handled like Job Processing cases: interview, offer and employer.
  const jobLike = module === "job" || module === "remote";
  const config = configOf(module);
  const { settings } = useSettings();
  const [stageTo, setStageTo] = useState<number | null>(null);
  const [emailTo, setEmailTo] = useState<"applicant" | "provider" | null>(null);
  const [review, setReview] = useState<{ doc: AppDocument; kind: "verify" | "reject" } | null>(null);
  const [viewing, setViewing] = useState<AppDocument | null>(null);
  const [pickAgent, setPickAgent] = useState(false);
  const [sendLetter, setSendLetter] = useState(false);
  const [note, setNote] = useState("");
  // Case box
  const [status, setStatus] = useState<AppStatus>(r.status);
  const [assigned, setAssigned] = useState(r.assigned_to?.id ?? "");
  const [deadline, setDeadline] = useState(r.deadline ?? "");
  const [interview, setInterview] = useState(localInput(r.interview_at));
  const [result, setResult] = useState<InterviewResult>(r.interview_result);
  const [salary, setSalary] = useState(r.offered_salary_usd ? String(r.offered_salary_usd) : "");
  const [reason, setReason] = useState("");
  const [fee, setFee] = useState(r.case_fee_poisha !== null ? String(r.case_fee_poisha / 100) : "");
  const [feeError, setFeeError] = useState("");
  const [caseError, setCaseError] = useState("");
  const [busy, setBusy] = useState(false);

  const answers = config.agent.fields.filter((f) => r.answers[f.key] !== undefined && r.answers[f.key] !== null && r.answers[f.key] !== "");
  const answerText = (v: unknown) => (v === true ? "Yes" : v === false ? "No" : String(v));

  async function saveCase(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    const changes: CaseChanges = {};
    if (assigned !== (r.assigned_to?.id ?? "")) changes.assigned_to = assigned || null;
    // Study and visa cases have a deadline; job, remote and visa cases an interview (visa: biometrics / interview).
    if (!jobLike && deadline !== (r.deadline ?? "")) changes.deadline = deadline || null;
    if (module !== "study") {
      if (interview !== localInput(r.interview_at)) changes.interview_at = interview || null;
      if (result !== r.interview_result) changes.interview_result = result;
    }
    if (jobLike) {
      const s = salary.trim();
      const current = r.offered_salary_usd ? String(r.offered_salary_usd) : "";
      if (s !== current) {
        if (s && !/^\d+$/.test(s)) return setCaseError("Offered salary must be a whole number of US dollars.");
        changes.offered_salary_usd = s ? Number(s) : null;
      }
    }
    const statusChanged = status !== r.status;
    if (!statusChanged && !Object.keys(changes).length) return setCaseError("Nothing changed.");
    if (statusChanged && (status === "rejected" || status === "on_hold") && !reason.trim()) {
      return setCaseError("Please give a reason (the applicant sees it).");
    }
    setBusy(true);
    try {
      if (statusChanged) await changeStatus(r.id, status, reason.trim());
      if (Object.keys(changes).length) await updateCase(r.id, changes);
      setCaseError("");
      setReason("");
      toast("Case saved.");
      onChanged();
    } catch (err) {
      if (isApiError(err) && err.code === "UNAUTHENTICATED") onSignedOut();
      else setCaseError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  // The fee for this case only. Whole taka above 0; empty or the item's fee means the item's fee.
  async function saveFee(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    const s = fee.trim();
    if (s && (!/^\d+$/.test(s) || Number(s) <= 0)) return setFeeError("The fee must be a whole number of taka above 0.");
    const poisha = s ? Number(s) * 100 : null;
    const next = poisha === null || poisha === r.item_fee_poisha ? null : poisha;
    if (next === r.fee_override_poisha) return setFeeError("Nothing changed.");
    setBusy(true);
    try {
      await setCaseFee(r.id, next);
      setFeeError("");
      toast("Fee saved.");
      onChanged();
    } catch (err) {
      if (isApiError(err) && err.code === "UNAUTHENTICATED") onSignedOut();
      else setFeeError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function addNote() {
    if (!note.trim()) return;
    try {
      await addInternalNote(r.id, note.trim());
      setNote("");
      toast("Note added.");
      onChanged();
    } catch (err) {
      onFail(err);
    }
  }

  const providerName = jobLike ? (r.item.employer ?? "the employer") : r.item.title;
  const flag = COUNTRY_FLAGS[r.item.country] ?? "🌐";

  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div className="cr" style={{ margin: "0 0 8px", gap: 8 }}>
        <span className={STATUS[r.status][1]}>{STATUS[r.status][0]}</span>
        <span className="bd in">{words.badge}</span>
        {r.self_apply ? <span className="bd info">Self Apply</span> : null}
        <span className={r.fee_paid ? "bd ok" : "bd warn"}>{r.fee_paid ? "Fee paid" : "Fee pending"}</span>
        {r.missing_count ? <span className="bd warn">{r.missing_count} documents missing</span> : null}
      </div>
      <h3 style={{ margin: "4px 0" }}>{r.applicant.name}</h3>
      <p>
        {r.item.title}
        {r.item.employer ? " · " + r.item.employer : ""} · {flag} {r.item.country}
      </p>
      <div className="kv">
        <div>
          <span>Ref</span>
          <b>{r.ref}</b>
        </div>
        <div>
          <span>Account ID</span>
          <b>{r.applicant.public_id}</b>
        </div>
        <div>
          <span>{words.who} email</span>
          <b>{r.applicant.email || "–"}</b>
        </div>
        <div>
          <span>Phone</span>
          <b>{r.applicant.phone || "–"}</b>
        </div>
        <div>
          <span>{module === "study" ? "University" : module === "visa" ? "Embassy" : "Employer"} email</span>
          <b>{r.provider_email || "–"}</b>
        </div>
        <div>
          <span>Started</span>
          <b>{formatDate(r.created_at)}</b>
        </div>
        <div>
          <span>Agent</span>
          <b>
            {r.agent ? r.agent.name + (r.agent.active ? "" : " (switched off)") : "Direct"}{" "}
            <button className="lk" type="button" onClick={() => setPickAgent(true)}>
              Change
            </button>
          </b>
        </div>
        {answers.map((f) => (
          <div key={f.key}>
            <span>{f.label}</span>
            <b>{answerText(r.answers[f.key])}</b>
          </div>
        ))}
      </div>

      <label className="fl" style={{ marginTop: 14 }}>
        <span>Processing stage</span>
        <select
          value={r.stage}
          disabled={r.status !== "active"}
          onChange={(e) => setStageTo(Number(e.target.value))}
          title={r.status !== "active" ? "The stage can change only while the application is active." : undefined}
        >
          {r.stages.map((s, i) => (
            <option key={s} value={i}>
              {i + 1}. {s}
            </option>
          ))}
        </select>
      </label>
      <div className="cr">
        <button className="btn ghost sm" type="button" onClick={() => setEmailTo("applicant")}>
          {words.emailApplicant}
        </button>
        <button className="btn ghost sm" type="button" disabled={!r.provider_email} onClick={() => setEmailTo("provider")}>
          {r.provider_email ? words.emailProvider : "No email on file"}
        </button>
      </div>
      {r.emails.length ? (
        <details style={{ marginTop: 8 }}>
          <summary style={{ cursor: "pointer", fontSize: 14, fontWeight: 600 }}>Messages sent ({r.emails.length})</summary>
          {r.emails.map((m) => (
            <small key={m.id} style={{ display: "block", color: "var(--muted)", marginTop: 4 }}>
              {formatDateTime(m.at)} · {m.channel === "email" ? "✉" : "💬"} {m.to} · {m.subject || "(WhatsApp)"} · {m.status}
              {m.status === "failed" ? (
                <>
                  {" · "}
                  <button className="lk" type="button" onClick={() => void resendNotification(m.id).then(onChanged, onFail)}>
                    Resend
                  </button>
                </>
              ) : null}
            </small>
          ))}
        </details>
      ) : null}

      {admin.role === "super_admin" ? (
        <form noValidate onSubmit={(e) => void saveFee(e)} style={{ marginTop: 16, borderTop: "1px solid var(--line)", paddingTop: 14 }}>
          <div className="fgrid">
            <label className="fl">
              <span>{r.self_apply ? "Self-apply fee for this case (৳)" : "Application fee for this case (৳)"}</span>
              <input
                type="number"
                min="1"
                step="1"
                value={fee}
                disabled={r.fee_locked}
                onChange={(e) => setFee(e.target.value)}
                placeholder={r.item_fee_poisha !== null ? String(r.item_fee_poisha / 100) : ""}
              />
            </label>
          </div>
          <small style={{ display: "block", color: "var(--muted)" }}>
            {r.fee_locked
              ? "Paid or payment started: this fee can no longer change."
              : "Item fee: " +
                (r.item_fee_poisha !== null ? formatMoney(r.item_fee_poisha) : "not set") +
                (r.fee_override_poisha !== null ? " · this case has its own fee" : "") +
                ". The applicant sees and pays this amount."}
          </small>
          <p className="err" role="alert">
            {feeError}
          </p>
          {r.fee_locked ? null : (
            <div className="cr" style={{ marginTop: 0 }}>
              <button className="btn sm" type="submit" disabled={busy}>
                Save fee
              </button>
              {r.fee_override_poisha !== null ? (
                <button
                  className="btn ghost sm"
                  type="button"
                  disabled={busy}
                  onClick={() => setFee(r.item_fee_poisha !== null ? String(r.item_fee_poisha / 100) : "")}
                >
                  Use item fee
                </button>
              ) : null}
            </div>
          )}
        </form>
      ) : null}

      <form noValidate onSubmit={(e) => void saveCase(e)} style={{ marginTop: 16, borderTop: "1px solid var(--line)", paddingTop: 14 }}>
        <div className="fgrid">
          <label className="fl">
            <span>Status</span>
            <select value={status} onChange={(e) => setStatus(e.target.value as AppStatus)} disabled={r.status === "withdrawn"}>
              {APP_STATUSES.filter((s) => s !== "withdrawn" || r.status === "withdrawn").map((s) => (
                <option key={s} value={s}>
                  {STATUS[s][0]}
                </option>
              ))}
            </select>
          </label>
          <label className="fl">
            <span>Assigned to</span>
            <select value={assigned} onChange={(e) => setAssigned(e.target.value)}>
              <option value="">Nobody</option>
              {r.assigned_to && !staff.some((s) => s.id === r.assigned_to?.id) ? <option value={r.assigned_to.id}>{r.assigned_to.name}</option> : null}
              {staff.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {s.id === admin.id ? " (me)" : ""}
                </option>
              ))}
            </select>
          </label>
          {!jobLike ? (
            <label className="fl">
              <span>{module === "visa" ? "Lodgement deadline" : "Application deadline"}</span>
              <input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
            </label>
          ) : null}
          {module !== "study" ? (
            <>
              <label className="fl">
                <span>{module === "visa" ? "Biometrics / interview date & time (Dhaka)" : "Interview date & time (Dhaka)"}</span>
                <input type="datetime-local" value={interview} onChange={(e) => setInterview(e.target.value)} />
              </label>
              <label className="fl">
                <span>Interview result</span>
                <select value={result} onChange={(e) => setResult(e.target.value as InterviewResult)}>
                  {INTERVIEW_RESULTS.map((x) => (
                    <option key={x} value={x}>
                      {RESULT[x]}
                    </option>
                  ))}
                </select>
              </label>
              {jobLike ? <TextField label="Offered salary (USD/month)" value={salary} onChange={setSalary} /> : null}
            </>
          ) : null}
          <TextField label="Reason / note to applicant (needed for On hold, Rejected or reopening)" value={reason} onChange={setReason} area={2} full />
        </div>
        <p className="err" role="alert">
          {caseError}
        </p>
        <button className="btn sm" type="submit" disabled={busy}>
          Save case
        </button>
      </form>

      <div style={{ marginTop: 18 }}>
        <h4 style={{ margin: "0 0 6px" }}>
          Documents {r.missing_count ? <span className="bd warn">{r.missing_count} missing</span> : <span className="bd ok">All uploaded</span>}
        </h4>
        {r.documents.length ? (
          r.documents.map((d) => (
            <div className="xrow" key={d.id}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <b>{d.type}</b>
                <small>
                  {d.original_name} · {formatDate(d.uploaded_at)}
                  {d.expiry ? " · expires " + formatDate(d.expiry) : ""}
                  {d.note ? " · " + d.note : ""}
                </small>
              </div>
              <div className="cr" style={{ margin: 0, gap: 8 }}>
                <span className={DOC_STATUS[d.shown_status][1]}>{DOC_STATUS[d.shown_status][0]}</span>
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
          ))
        ) : (
          <p style={{ color: "var(--muted)", margin: 0, fontSize: 14 }}>Nothing uploaded yet.</p>
        )}
      </div>

      {r.status !== "withdrawn" || r.letter ? (
        <div style={{ marginTop: 18 }}>
          <h4 style={{ margin: "0 0 6px" }}>
            Completion letter{" "}
            {r.letter ? (
              r.letter.valid ? (
                <span className="bd ok">Issued</span>
              ) : (
                <span className="bd no">Not valid (case reopened)</span>
              )
            ) : (
              <span className="bd">Not issued</span>
            )}
          </h4>
          <div className="xrow">
            <div style={{ minWidth: 0, flex: 1 }}>
              <b>{r.letter ? r.letter.id : "Draft preview"}</b>
              <small>
                {r.letter
                  ? "Issued " + formatDate(r.letter.issued_at)
                  : r.status === "completed"
                    ? "Issue the letter to send it to the client."
                    : "You can issue it once the case is completed (last stage, or status Completed)."}
              </small>
            </div>
            <div className="cr" style={{ margin: 0, gap: 8 }}>
              <a className="lk" href={caseLetterPdfUrl(r.id)} target="_blank" rel="noopener">
                View
              </a>
              <a className="lk" href={caseLetterPdfUrl(r.id, true)}>
                Download PDF
              </a>
              {r.letter ? (
                r.letter.valid ? (
                  <button type="button" className="btn sm" onClick={() => setSendLetter(true)}>
                    Send
                  </button>
                ) : null
              ) : r.status !== "completed" ? null : (
                <button
                  type="button"
                  className="btn sm"
                  onClick={() =>
                    void issueCaseLetter(r.id)
                      .then((l) => {
                        toast("Completion letter " + l.id + " issued.");
                        onChanged();
                      })
                      .catch(onFail)
                  }
                >
                  Issue completion letter
                </button>
              )}
            </div>
          </div>
        </div>
      ) : null}

      <details style={{ marginTop: 16 }}>
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>History ({r.history.length})</summary>
        <div className="hist" style={{ marginTop: 8 }}>
          {r.history.map((e) => (
            <div key={e.id}>
              <b>{e.text}</b> {e.public ? null : <span className="bd">internal</span>}
              {e.note ? (
                <>
                  <br />
                  {e.note}
                </>
              ) : null}
              <small>
                {formatDateTime(e.at)} · {e.by_name}
              </small>
            </div>
          ))}
        </div>
      </details>
      <div className="cr" style={{ alignItems: "flex-end" }}>
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Add internal note (only staff see it)"
          aria-label="Add internal note"
          style={{ flex: 1, minWidth: 0 }}
        />
        <button className="btn ghost sm" type="button" onClick={() => void addNote()} disabled={!note.trim()}>
          Add note
        </button>
      </div>

      {stageTo !== null ? (
        <StageDialog
          appId={r.id}
          stageName={r.stages[stageTo]}
          stage={stageTo}
          onClose={() => setStageTo(null)}
          onDone={() => {
            setStageTo(null);
            toast("Stage saved.");
            onChanged();
          }}
          onSignedOut={onSignedOut}
        />
      ) : null}
      {emailTo ? (
        <EmailDialog
          row={r}
          to={emailTo}
          company={settings?.name ?? ""}
          providerName={providerName}
          onClose={() => setEmailTo(null)}
          onDone={() => {
            setEmailTo(null);
            toast("Message queued.");
            onChanged();
          }}
          onSignedOut={onSignedOut}
        />
      ) : null}
      {viewing ? <DocumentViewer doc={viewing} onClose={() => setViewing(null)} /> : null}
      {sendLetter && r.letter ? (
        <SendDocumentDialog
          title={"Send completion letter " + r.letter.id}
          email={r.applicant.email}
          phone={r.applicant.phone || null}
          send={(channels) => sendCaseLetter(r.id, channels)}
          onClose={() => setSendLetter(false)}
          onDone={(n) => {
            setSendLetter(false);
            toast(n + (n === 1 ? " message" : " messages") + " queued.");
            onChanged();
          }}
          onSignedOut={onSignedOut}
        />
      ) : null}
      {pickAgent ? (
        <CaseAgentDialog row={r} module={module} onClose={() => setPickAgent(false)} onDone={() => (setPickAgent(false), toast("Agent saved."), onChanged())} onSignedOut={onSignedOut} />
      ) : null}
      {review?.kind === "verify" ? (
        <VerifyDocDialog doc={review.doc} onClose={() => setReview(null)} onDone={() => (setReview(null), toast("Document verified."), onChanged())} onSignedOut={onSignedOut} />
      ) : null}
      {review?.kind === "reject" ? (
        <RejectDocDialog doc={review.doc} onClose={() => setReview(null)} onDone={() => (setReview(null), toast("Document rejected."), onChanged())} onSignedOut={onSignedOut} />
      ) : null}
    </div>
  );
}

type StageProps = { appId: string; stage: number; stageName: string; onClose: () => void; onDone: () => void; onSignedOut: () => void };

function StageDialog({ appId, stage, stageName, onClose, onDone, onSignedOut }: StageProps) {
  const [note, setNote] = useState("");
  const [notify, setNotify] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      await changeStage(appId, stage, note.trim(), notify);
      onDone();
    } catch (err) {
      if (isApiError(err) && err.code === "UNAUTHENTICATED") return onSignedOut();
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <Modal open title={"Move to: " + stageName} onClose={onClose}>
      <form noValidate onSubmit={(e) => void save(e)}>
        <div className="fgrid">
          <TextField label="Note to the applicant (optional)" value={note} onChange={setNote} area={3} full />
          <label className="simf" style={{ gridColumn: "1/-1" }}>
            <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} /> Email / WhatsApp the applicant about this change
          </label>
        </div>
        <p className="err" role="alert">
          {error}
        </p>
        <div className="cr" style={{ margin: 0 }}>
          <button className="btn" type="submit" disabled={busy}>
            Save stage
          </button>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}

type EmailProps = {
  row: CaseRow;
  to: "applicant" | "provider";
  company: string;
  providerName: string;
  onClose: () => void;
  onDone: () => void;
  onSignedOut: () => void;
};

// The email dialog of the reference, pre-filled with the applicant update or the provider letter.
function EmailDialog({ row: r, to, company, providerName, onClose, onDone, onSignedOut }: EmailProps) {
  const applicant = to === "applicant";
  const [subject, setSubject] = useState(applicant ? "Update on your application " + r.ref : "Application of " + r.applicant.name + " (" + r.ref + ")");
  const [body, setBody] = useState(
    applicant
      ? "Dear " + r.applicant.name + ",\n\nYour application " + r.ref + " for " + r.item.title + " is now at: " + r.stage_name + ".\n\n\nBest regards,\n" + company
      : "Dear " +
          providerName +
          ",\n\nWe are writing about our candidate " +
          r.applicant.name +
          " (" +
          (r.applicant.email ?? "no email") +
          ") for " +
          r.item.title +
          ".\n\n\nBest regards,\n" +
          company,
  );
  const [channels, setChannels] = useState<Channel[]>(
    (["email", "whatsapp"] as Channel[]).filter((c) => (c === "email" ? !!r.applicant.email : !!r.applicant.phone)),
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function send(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    if (applicant && !channels.length) return setError("Please choose email, WhatsApp or both.");
    if (!subject.trim() || !body.trim()) return setError("Please write the subject and the message.");
    setBusy(true);
    try {
      await sendCaseEmail(r.id, to, subject.trim(), body.trim(), applicant ? channels : undefined);
      onDone();
    } catch (err) {
      if (isApiError(err) && err.code === "UNAUTHENTICATED") return onSignedOut();
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <Modal open title={applicant ? "Message the applicant" : "Email the " + WORDS[r.module].provider} onClose={onClose}>
      <form noValidate onSubmit={(e) => void send(e)}>
        {applicant ? null : <p className="sub">To: {r.provider_email}</p>}
        <div className="fgrid">
          {applicant ? <ChannelPicker value={channels} onChange={setChannels} email={r.applicant.email} phone={r.applicant.phone || null} /> : null}
          <TextField label="Subject" value={subject} onChange={setSubject} required full />
          <TextField label="Message" value={body} onChange={setBody} area={8} required full />
        </div>
        <p className="err" role="alert">
          {error}
        </p>
        <div className="cr" style={{ margin: 0 }}>
          <button className="btn" type="submit" disabled={busy}>
            Send
          </button>
          <button className="btn ghost" type="button" onClick={() => void navigator.clipboard?.writeText(subject + "\n\n" + body)}>
            Copy text
          </button>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}
