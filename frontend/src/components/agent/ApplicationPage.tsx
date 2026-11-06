"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ChangeEvent, type CSSProperties } from "react";
import {
  COUNTRY_FLAGS,
  isApiError,
  lastAgentInputs,
  MAX_UPLOAD_BYTES,
  myApplications,
  NETWORK_MESSAGE,
  startApplication,
  submitDocuments,
  uploadDocument,
  withdrawApplication,
  getMyApplication,
  myLetterPdfUrl,
  type AppDocument,
  type AppModule,
  type AppStatus,
  type MyApplication,
  type PayStart,
  type ShownDocStatus,
} from "@/lib/api";
import { formatDate, formatDateTime, formatMoney } from "@/lib/format";
import { useToast } from "../admin/Toast";
import Button from "../Button";
import LoadError from "../LoadError";
import { configOf } from "../modules";
import InvoiceDialog from "../payment/InvoiceDialog";
import { METHOD_NAMES } from "../payment/methods";
import { useSession } from "../SessionProvider";
import DocumentViewer from "./DocumentViewer";
import FeeDialog from "./FeeDialog";

// Badge text and colour per application status (STS in the reference).
const STATUS: Record<AppStatus, [string, string]> = {
  active: ["Active", "ok"],
  on_hold: ["On hold", "warn"],
  rejected: ["Rejected", "no"],
  withdrawn: ["Withdrawn", ""],
  completed: ["Completed", "info"],
};

// Badge text and colour per document status (DST in the reference).
const DOC_STATUS: Partial<Record<ShownDocStatus, [string, string]>> = {
  pending: ["Waiting review", "warn"],
  verified: ["Verified", "ok"],
  rejected: ["Rejected", "no"],
  expiring: ["Expiring soon", "warn"],
  expired: ["Expired", "no"],
};


// The application page (showApply() and enhanceApply() in the reference) for any module with
// applications. id is the item slug.
export default function ApplicationPage({ module, slug: id }: { module: AppModule; slug: string }) {
  const config = configOf(module);
  const router = useRouter();
  const { session, reload, openAuth } = useSession();
  const { toast, toastNode } = useToast();
  // undefined while loading; null when the item does not exist.
  const [detail, setDetail] = useState<MyApplication | null | undefined>(undefined);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  // Files chosen per document type, saved together with "Submit documents".
  const [staged, setStaged] = useState<Record<string, File>>({});
  const [submitting, setSubmitting] = useState(false);
  // Documents and History share one card, one tab at a time.
  const [tab, setTab] = useState<"docs" | "history">("docs");
  const [paying, setPaying] = useState(false);
  const [showInvoice, setShowInvoice] = useState(false);
  const [viewing, setViewing] = useState<AppDocument | null>(null);
  const appId = useRef<string | null>(null);
  const accountId = useRef<string | null>(null);
  const account = session?.applicants[module];
  const signedOut = session !== null && !account;

  const load = useCallback(async (): Promise<MyApplication | null> => {
    if (!appId.current) {
      // The newest application for this item, whatever its status; only if there is none, a new one
      // with the agent form answers as the application answers.
      const mine = (await myApplications(module)).filter((a) => a.item_slug === id);
      const existing = mine.sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
      try {
        if (existing) appId.current = existing.id;
        else {
          const keys = new Set(configOf(module).agent.fields.map((f) => f.key));
          const last = (await lastAgentInputs(module)) ?? {};
          const answers = Object.fromEntries(Object.entries(last).filter(([k]) => keys.has(k)));
          appId.current = (await startApplication(module, id, answers)).id;
        }
      } catch (err) {
        if (isApiError(err) && err.code === "NOT_FOUND") return null;
        throw err;
      }
    }
    return getMyApplication(module, appId.current);
  }, [module, id]);

  useEffect(() => {
    let live = true;
    if (!account) return;
    // Another account signed in: forget the previous person's application.
    if (accountId.current !== account.id) {
      accountId.current = account.id;
      appId.current = null;
    }
    void load()
      .then((d) => {
        if (live) {
          setDetail(d);
          setError("");
        }
      })
      .catch((err: unknown) => {
        if (!live) return;
        // The sign-in ended (signed out, another account, or expired): read the session again, so the
        // page sends the person to sign in instead of staying empty.
        if (isApiError(err) && err.code === "UNAUTHENTICATED") {
          appId.current = null;
          void reload();
          return;
        }
        if (!(isApiError(err) && err.code === "MODULE_NOT_LICENSED")) {
          setError(isApiError(err) ? err.message : NETWORK_MESSAGE);
        }
      });
    return () => {
      live = false;
    };
  }, [account, load, attempt, reload]);

  // Not signed in: back to the item page with the auth dialog; the application opens after sign-in.
  useEffect(() => {
    if (!signedOut) return;
    const here = config.base + "/" + id + "/apply";
    router.replace(config.base + "/" + id);
    openAuth({ mode: "up", module, note: config.apply.authNote, after: () => router.push(here) });
  }, [signedOut, config, id, module, router, openAuth]);

  async function refresh() {
    setDetail(await load());
  }

  if (error) return <LoadError message={error} onRetry={() => setAttempt(attempt + 1)} />;
  if (!account || detail === undefined) return <p className="wrap">Loading…</p>;
  if (detail === null) {
    return (
      <section>
        <div className="wrap">
          <div className="card">
            <h3>Not found</h3>
            <div className="cr">
              <Button variant="ghost" size="sm" href={config.base}>
                {config.item.notFoundLink}
              </Button>
            </div>
          </div>
        </div>
      </section>
    );
  }

  const app = detail;
  const { stages, payment, invoice } = detail;
  const place = config.describe(detail.item);
  const active = app.status === "active";
  const canPay = active || app.status === "on_hold";
  const pct = Math.round((app.stage / (stages.length - 1)) * 100);
  const fee = detail.fee_poisha ?? payment?.amount_poisha ?? detail.item.fee_poisha;
  const waiting = payment?.status === "pending_verify" ? payment : null;
  const reason = detail.history.find((e) => e.note && e.text.startsWith("Status"))?.note ?? "";
  const answers = config.agent.fields.filter((f) => app.answers[f.key] !== undefined);
  const selfMode = app.self_apply;
  const shownTab = selfMode ? "history" : tab;
  const submittedAt = detail.documents_submitted_at;
  const stagedCount = Object.keys(staged).length;
  const uploadedCount = detail.required_types.length - detail.missing_count;
  // New uploads after the last submission (or none yet) still have to be submitted.
  const unsent = detail.documents.some((d) => !submittedAt || Date.parse(d.uploaded_at) > Date.parse(submittedAt));
  const canSubmit = active && !submitting && (stagedCount > 0 || (detail.missing_count === 0 && unsent));
  // The processing stage the documents move the case to.
  const docsStage = Math.min(1, stages.length - 1);

  function choose(type: string, e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!/\.(pdf|jpe?g|png)$/i.test(file.name)) {
      toast("Only PDF, JPG or PNG files.", true);
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      toast("File is too large (max 2 MB).", true);
      return;
    }
    setStaged((s) => ({ ...s, [type]: file }));
  }

  function unstage(type: string) {
    setStaged((s) => {
      const rest = { ...s };
      delete rest[type];
      return rest;
    });
  }

  // Saves every chosen file, then sends the documents to review once all required ones are in.
  async function submitAll() {
    setSubmitting(true);
    try {
      for (const type of detail ? detail.required_types : []) {
        const file = staged[type];
        if (!file) continue;
        await uploadDocument(module, app.id, type, file);
        unstage(type);
      }
      const fresh = await load();
      setDetail(fresh);
      if (!fresh) return;
      if (fresh.missing_count) {
        toast("Documents saved. " + fresh.missing_count + " still needed before they go to review.");
        return;
      }
      setDetail(await submitDocuments(module, app.id));
      toast("Documents submitted. Our team will review them.");
    } catch (err) {
      toast(isApiError(err) ? err.message : "Something went wrong. Please try again.", true);
      void refresh().catch(() => undefined);
    } finally {
      setSubmitting(false);
    }
  }

  async function withdraw() {
    if (!window.confirm("Withdraw this application? Fees already paid follow our refund policy.")) return;
    try {
      await withdrawApplication(module, app.id);
      await refresh();
    } catch (err) {
      toast(isApiError(err) ? err.message : "Something went wrong. Please try again.", true);
    }
  }

  // Only bank / office payments come back here; card and bKash payments go to the gateway.
  function paid(result: PayStart) {
    setPaying(false);
    void reload();
    if (result.status === "pending_verify") toast("Payment reference sent for verification.");
    void refresh();
  }

  function chooseButton(type: string, again: boolean) {
    if (submitting) return null;
    return (
      <label className={"btn sm" + (again ? " ghost" : "")}>
        {again ? "Choose again" : "Choose file"}
        <input type="file" hidden accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => choose(type, e)} />
      </label>
    );
  }

  // A chosen file that is not saved yet.
  function stagedRow(type: string) {
    const file = staged[type];
    return (
      <div className="xrow" key={type}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <b>{type}</b>
          <small>
            {file.name} · {Math.max(1, Math.round(file.size / 1024))} KB
          </small>
        </div>
        <div className="cr" style={{ margin: 0, gap: 8 }}>
          <span className="bd info">{submitting ? "Saving…" : "Ready to submit"}</span>
          {submitting ? null : (
            <button type="button" className="lk r" onClick={() => unstage(type)}>
              Remove
            </button>
          )}
        </div>
      </div>
    );
  }

  let next;
  if (!app.fee_paid) {
    next = waiting ? (
      <div className="banner in" style={{ margin: 0 }}>
        {waiting.method === "manual" ? "Your payment reference " + (waiting.manual_ref ?? "") : "Your payment"} (
        {formatMoney(waiting.amount_poisha)}) is waiting for verification by our finance team.
      </div>
    ) : (
      <>
        <p style={{ marginBottom: 16 }}>
          {selfMode ? "Pay the Self Apply fee of " : config.apply.lockedBefore}
          <b>{formatMoney(fee)}</b>
          {selfMode
            ? " to unlock the official application link. You then apply on the university website by yourself."
            : config.apply.lockedAfter}
        </p>
        {payment && (payment.status === "rejected" || payment.status === "failed" || payment.status === "cancelled") ? (
          <div className="banner no">
            Your last payment was {payment.status === "rejected" ? "not accepted" : payment.status}.
            {payment.note ? " " + payment.note : ""} You can pay again.
          </div>
        ) : null}
        {canPay ? (
          <button className="btn" type="button" onClick={() => setPaying(true)}>
            🔒 Pay {formatMoney(fee)}
            {config.apply.payButtonSuffix}
          </button>
        ) : null}
      </>
    );
  } else {
    next = (
      <>
        {payment ? (
          <p style={{ margin: "0 0 16px", fontWeight: 600, color: "#16A34A" }}>
            ✓ Fee paid · {formatMoney(payment.amount_poisha)} via {METHOD_NAMES[payment.method]}
          </p>
        ) : null}
        {invoice ? (
          <p style={{ margin: "0 0 16px" }}>
            🧾 Invoice <b>{invoice.no}</b> generated. Confirmation email to {invoice.email}: <b>{invoice.email_status === "sent" ? "sent" : "on its way"}</b>
            <br />
            <button className="btn ghost sm" type="button" style={{ marginTop: 10 }} onClick={() => setShowInvoice(true)}>
              View / print invoice
            </button>
          </p>
        ) : null}
        <p style={{ marginBottom: config.apply.hasLink ? 16 : 0 }}>
          {selfMode
            ? "Apply on the university website by yourself. Our team does not process or track a Self Apply."
            : config.apply.paidText}
        </p>
        {config.apply.hasLink ? (
          detail.apply_link && /^https?:\/\//.test(detail.apply_link) ? (
            <a className="btn" href={detail.apply_link} target="_blank" rel="noopener">
              {config.apply.linkButton}
            </a>
          ) : (
            <button className="btn" type="button" disabled>
              {config.apply.noLink}
            </button>
          )
        ) : null}
      </>
    );
  }

  return (
    <div style={{ "--a": config.accent } as CSSProperties}>
      {active ? null : (
        <div className="wrap" style={{ marginTop: 24 }}>
          <div className={"banner" + (app.status === "rejected" ? " no" : app.status === "completed" ? " ok" : "")}>
            This application is {STATUS[app.status][0].toLowerCase()}.{reason ? " " + reason : ""}
          </div>
        </div>
      )}
      <div className="hero">
        <div className="wrap">
          <div>
            <Link className="crumb" href={config.base + "/" + id}>
              ← Back to details
            </Link>
            <br />
            <span className="tag">{selfMode ? "Self Apply" : "Your application"}</span>
            <h1>{place.name}</h1>
            <p className="lead">
              {COUNTRY_FLAGS[place.country] ?? ""} {place.country} · {place.place}. Started {formatDate(app.created_at)}.
            </p>
          </div>
          {selfMode ? (
            <div className="vis">
              <h3>{app.fee_paid ? "Fee paid" : "Fee pending"}</h3>
              <p style={{ color: "var(--muted)", margin: 0 }}>
                {app.fee_paid
                  ? "Your official application link is ready below."
                  : "Pay the Self Apply fee to unlock the official application link."}
              </p>
            </div>
          ) : (
            <div className="vis">
              <h3>Progress: {pct}%</h3>
              <p style={{ color: "var(--muted)", margin: 0 }}>
                Stage {app.stage + 1} of {stages.length}: {stages[app.stage]}
              </p>
              <div className="bar">
                <i style={{ width: pct + "%" }}></i>
              </div>
            </div>
          )}
        </div>
      </div>
      <section>
        <div className="wrap pf ap" style={{ gridTemplateColumns: selfMode ? "1fr" : "1fr 1fr" }}>
          {selfMode ? null : (
            <div className="card">
              <h3>Processing stages</h3>
              {stages.map((name, i) => {
                const done = i < app.stage;
                const now = i === app.stage;
                return (
                  <div className={"st" + (done ? " done" : now ? " now" : "")} key={name}>
                    <span className="dot">{done ? "✓" : i + 1}</span>
                    <div>
                      <b>{name}</b>
                      <small>{done ? "Completed" : now ? "You are here" : "Upcoming"}</small>
                      {i === 0 && now && active ? (
                        <small>
                          Documents: {uploadedCount} of {detail.required_types.length} uploaded. Submit them all to move to the next
                          stage.
                        </small>
                      ) : null}
                      {i === docsStage && submittedAt ? <small>Documents submitted {formatDateTime(submittedAt)}</small> : null}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          <div>
            <div className="card">
              <h3>Next step</h3>
              {next}
            </div>
            {detail.letter ? (
              <div className="card" style={{ marginTop: 18 }}>
                <h3>Completion letter</h3>
                {detail.letter.valid ? (
                  <>
                    <p style={{ margin: "0 0 12px" }}>
                      Your completion letter {detail.letter.id} was issued on {formatDate(detail.letter.issued_at)}. Anyone can check it on our
                      Verify certificate page.
                    </p>
                    <div className="cr" style={{ margin: 0 }}>
                      <a className="btn" href={myLetterPdfUrl(module, app.id, true)}>
                        Download letter (PDF)
                      </a>
                      <a className="btn ghost" href={myLetterPdfUrl(module, app.id)} target="_blank" rel="noopener">
                        View
                      </a>
                    </div>
                  </>
                ) : (
                  <p style={{ margin: 0, color: "var(--muted)" }}>Your case was reopened, so the letter is not valid at the moment.</p>
                )}
              </div>
            ) : null}
            {/* Your details and Status side by side (stacked on narrow screens). */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 18, marginTop: 18 }}>
              {answers.length ? (
                <div className="card">
                  <h3>Your details</h3>
                  <div className="kv">
                    {answers.map((f) => (
                      <div key={f.key}>
                        <span>{f.label}</span>
                        <b>{answerText(app.answers[f.key])}</b>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
              <div className="card">
                <h3>Status</h3>
                <div className="kv">
                  <div>
                    <span>Status</span>
                    <b>
                      <span className={"bd " + STATUS[app.status][1]}>{STATUS[app.status][0]}</span>
                    </b>
                  </div>
                  {detail.advisor_name ? (
                    <div>
                      <span>Your advisor</span>
                      <b>{detail.advisor_name}</b>
                    </div>
                  ) : null}
                  {app.deadline ? (
                    <div>
                      <span>Application deadline</span>
                      <b>{formatDate(app.deadline)}</b>
                    </div>
                  ) : null}
                  {app.interview_at ? (
                    <div>
                      <span>Interview</span>
                      <b>
                        {formatDateTime(app.interview_at)}
                        {app.interview_result && app.interview_result !== "pending" ? " · " + (app.interview_result === "passed" ? "Passed" : "Not passed") : ""}
                      </b>
                    </div>
                  ) : null}
                  {app.offered_salary_usd ? (
                    <div>
                      <span>Job offer</span>
                      <b>${app.offered_salary_usd.toLocaleString("en-US")} per month</b>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
            <div className="card" style={{ marginTop: 18 }}>
              {selfMode ? (
                <h3>History</h3>
              ) : (
                <div className="seg" role="tablist" aria-label="Documents and history">
                  <button type="button" role="tab" aria-selected={tab === "docs"} onClick={() => setTab("docs")}>
                    Documents ({uploadedCount}/{detail.required_types.length})
                  </button>
                  <button type="button" role="tab" aria-selected={tab === "history"} onClick={() => setTab("history")}>
                    History ({detail.history.length})
                  </button>
                </div>
              )}
              {shownTab === "docs" ? (
                <>
                  <p className="sub" style={{ margin: "0 0 6px", fontSize: 14 }}>
                    PDF, JPG or PNG, up to 2 MB. Only you and our staff can see them.
                  </p>
                  {detail.missing_count ? (
                    <p className="banner in" style={{ margin: "0 0 6px" }}>
                      {detail.missing_count} of {detail.required_types.length} documents still needed.
                    </p>
                  ) : submittedAt && !unsent ? (
                    <p className="banner ok" style={{ margin: "0 0 6px" }}>
                      All documents submitted {formatDateTime(submittedAt)}. Our team is reviewing them.
                    </p>
                  ) : null}
                  {detail.required_types.map((type) => {
                    const d = detail.documents.find((x) => x.type === type);
                    if (staged[type]) return stagedRow(type);
                    if (!d) {
                      return (
                        <div className="xrow" key={type}>
                          <div>
                            <b>{type}</b>
                            <small>Not uploaded</small>
                          </div>
                          {active ? chooseButton(type, false) : null}
                        </div>
                      );
                    }
                    const [label, colour] = DOC_STATUS[d.shown_status] ?? ["–", ""];
                    const again = active && (d.shown_status === "rejected" || d.shown_status === "expired" || d.shown_status === "expiring");
                    return (
                      <div className="xrow" key={type}>
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <b>{type}</b>
                          <small>
                            {d.original_name} · {Math.max(1, Math.round(d.size_bytes / 1024))} KB · {formatDate(d.uploaded_at)}
                            {d.expiry ? " · expires " + formatDate(d.expiry) : ""}
                            {d.note ? " · " + d.note : ""}
                          </small>
                        </div>
                        <div className="cr" style={{ margin: 0, gap: 8 }}>
                          <span className={"bd " + colour}>{label}</span>
                          <button type="button" className="lk" onClick={() => setViewing(d)}>
                            View
                          </button>
                          {again ? chooseButton(type, true) : null}
                        </div>
                      </div>
                    );
                  })}
                  {active ? (
                    <div className="cr" style={{ margin: "14px 0 0" }}>
                      <button className="btn" type="button" disabled={!canSubmit} onClick={() => void submitAll()}>
                        {submitting ? "Submitting…" : "Submit documents"}
                      </button>
                    </div>
                  ) : null}
                </>
              ) : (
                <>
                  <div className="hist">
                    {detail.history.map((e) => (
                      <div key={e.id}>
                        <b>{e.text}</b>
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
                  {active ? (
                    <p style={{ margin: "14px 0 0" }}>
                      <button type="button" className="lk r" onClick={() => void withdraw()}>
                        Withdraw this application
                      </button>
                    </p>
                  ) : null}
                </>
              )}
            </div>
          </div>
        </div>
      </section>
      {paying ? (
        <FeeDialog
          module={module}
          applicationId={app.id}
          itemName={place.name}
          country={place.country}
          fee_poisha={fee}
          phone={account.phone}
          onClose={() => setPaying(false)}
          onDone={paid}
        />
      ) : null}
      <InvoiceDialog invoice={invoice} open={showInvoice} onClose={() => setShowInvoice(false)} />
      {viewing ? <DocumentViewer doc={viewing} onClose={() => setViewing(null)} /> : null}
      {toastNode}
    </div>
  );
}


// An answer as people read it: yes / no for true / false, a dash when empty.
function answerText(value: unknown): string {
  if (value === true) return "Yes";
  if (value === false) return "No";
  return value === null || value === undefined || value === "" ? "–" : String(value);
}
