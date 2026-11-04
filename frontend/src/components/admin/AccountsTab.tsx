"use client";

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  addLedgerEntry,
  approveRefund,
  declineRefund,
  isApiError,
  LEDGER_CATEGORIES,
  LEDGER_METHODS,
  ledgerCsvUrl,
  ledgerSummary,
  listInvoices,
  listLedger,
  listOutstanding,
  listPendingPayments,
  listRefunds,
  rejectPayment,
  reverseLedgerEntry,
  sendPaymentReminder,
  verifyPayment,
  type Invoice,
  type LedgerDirection,
  type LedgerEntry,
  type LedgerPeriod,
  type LedgerSummary,
  type OutstandingItem,
  type PendingPayment,
  type Refund,
  type AdminUser,
} from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import Modal from "../Modal";
import { useSettings } from "../SettingsProvider";
import { errorText } from "../auth/messages";
import InvoiceDialog from "../payment/InvoiceDialog";
import AdminTable from "./AdminTable";
import CommissionsPanel from "./CommissionsPanel";
import { TextField } from "./Field";
import TabPage from "./TabPage";
import { handleFailure } from "./failure";
import type { ShowToast } from "./Toast";

const GREEN = "#16A34A";
const RED = "#DC2626";
const big = (color?: string) => ({ display: "block", font: "700 26px var(--font-sora)", color: color ?? "var(--text)" }) as const;
const today = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Dhaka" });

// One bar list of the reference bars(): label, amount and a bar of the share.
function Bars({ data, total, label }: { data: Record<string, number>; total: number; label?: (key: string) => string }) {
  const keys = Object.keys(data).sort((a, b) => data[b] - data[a]);
  if (!keys.length) return <p style={{ color: "var(--muted)", margin: 0 }}>No data yet.</p>;
  return keys.map((k) => (
    <div key={k} style={{ margin: "14px 0 0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, fontSize: 15 }}>
        <span>{label ? label(k) : k}</span>
        <b>{formatMoney(data[k])}</b>
      </div>
      <div className="bar" style={{ marginTop: 6 }}>
        <i style={{ width: Math.max(2, Math.round((100 * data[k]) / (total || 1))) + "%" }}></i>
      </div>
    </div>
  ));
}

type Props = { admin?: AdminUser; toast: ShowToast; onSignedOut: () => void };

// The Accounts tab (showAccounts() in the reference, spec F09): super admin and finance only.
export default function AccountsTab({ admin, toast, onSignedOut }: Props) {
  const { licence } = useSettings();
  const commissionSections = (["study", "job", "visa"] as const).filter((m) => licence?.modules[m]);
  const [period, setPeriod] = useState<LedgerPeriod>("all");
  const [direction, setDirection] = useState<LedgerDirection | "all">("all");
  const [page, setPage] = useState(1);
  const [summary, setSummary] = useState<LedgerSummary | null>(null);
  const [ledger, setLedger] = useState<{ items: LedgerEntry[]; total: number; page_size: number } | null>(null);
  const [pending, setPending] = useState<PendingPayment[]>([]);
  const [refunds, setRefunds] = useState<Refund[]>([]);
  const [outstanding, setOutstanding] = useState<{ items: OutstandingItem[]; total_poisha: number }>({ items: [], total_poisha: 0 });
  const [search, setSearch] = useState("");
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [shownInvoice, setShownInvoice] = useState<Invoice | null>(null);
  const [dialog, setDialog] = useState<ReactNode>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [s, l, p, r, o] = await Promise.all([
        ledgerSummary(period),
        listLedger(direction, period, page),
        listPendingPayments(),
        listRefunds(),
        listOutstanding(),
      ]);
      setSummary(s);
      setLedger(l);
      setPending(p);
      setRefunds(r);
      setOutstanding(o);
      setError("");
    } catch (err) {
      handleFailure(err, () => setError(errorText(err)), onSignedOut);
    }
  }, [period, direction, page, onSignedOut]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    let live = true;
    const timer = setTimeout(() => {
      void listInvoices(search)
        .then((page) => {
          if (live) setInvoices(page.items);
        })
        .catch(() => {});
    }, 200);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [search]);

  if (error) return <div className="banner no">{error}</div>;
  if (!summary || !ledger) return null;

  const close = () => setDialog(null);
  const done = (message: string) => {
    setDialog(null);
    toast(message);
    void load();
  };
  const fail = (err: unknown) => {
    if (isApiError(err) && err.code === "CONFLICT") {
      toast("Already done.", true);
      void load();
      return;
    }
    handleFailure(err, toast, onSignedOut);
  };
  const pl = period === "all" ? "All time" : "This month";
  const label = (k: string) => summary.category_labels[k] ?? k;
  const openRefunds = refunds.filter((r) => r.status === "requested");

  function verify(p: PendingPayment) {
    setDialog(
      <Confirm
        title="Verify payment"
        text={"Confirm that " + formatMoney(p.amount_poisha) + (p.manual_ref ? " with reference " + p.manual_ref : "") + " has arrived in your account?"}
        button="Verify"
        onClose={close}
        onYes={() => verifyPayment(p.id).then(() => done("Payment verified."), fail)}
      />,
    );
  }

  return (
    <TabPage title="Accounts" sub="Money in and out, payments to verify, refunds and what is still owed.">
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", marginBottom: 18 }}>
        <div className="card">
          <b style={big(summary.balance_all_time_poisha < 0 ? RED : undefined)}>{formatMoney(summary.balance_all_time_poisha)}</b>
          Current balance (all time)
        </div>
        <div className="card">
          <b style={big(GREEN)}>{formatMoney(summary.in_poisha)}</b>Money in · {pl}
        </div>
        <div className="card">
          <b style={big(RED)}>{formatMoney(summary.out_poisha)}</b>Money out · {pl}
        </div>
        <div className="card">
          <b style={big(summary.net_poisha < 0 ? RED : undefined)}>{formatMoney(summary.net_poisha)}</b>Net · {pl}
        </div>
      </div>
      <div className="seg" style={{ maxWidth: 300, marginBottom: 22 }}>
        {(
          [
            ["all", "All time"],
            ["month", "This month"],
          ] as const
        ).map(([p, text]) => (
          <button key={p} type="button" role="tab" aria-selected={period === p} onClick={() => (setPage(1), setPeriod(p))}>
            {text}
          </button>
        ))}
      </div>
      <div className="acc2">
        <div className="card">
          <h3>Where money came from</h3>
          <Bars data={summary.by_source} total={summary.in_poisha} label={label} />
        </div>
        <div className="card">
          <h3>Received through</h3>
          <Bars data={summary.by_method} total={summary.in_poisha} />
        </div>
        <div className="card">
          <h3>Where money went</h3>
          <Bars data={summary.by_expense} total={summary.out_poisha} label={label} />
        </div>
      </div>

      <div className="acc2">
        <div className="card">
          <h3>Payments to verify ({pending.length})</h3>
          {pending.length ? (
            pending.map((p) => (
              <div className="xrow" key={p.id}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <b>{p.name}</b>
                  <small>
                    {p.purpose} · {p.method_label}
                    {p.manual_ref ? " · ref " + p.manual_ref : ""} · {formatDate(p.created_at)}
                    {p.note ? " · " + p.note : ""}
                  </small>
                </div>
                <div className="cr" style={{ margin: 0, gap: 8 }}>
                  <b>{formatMoney(p.amount_poisha)}</b>
                  <button className="btn sm" type="button" onClick={() => verify(p)}>
                    Verify
                  </button>
                  <button
                    className="btn ghost sm"
                    type="button"
                    onClick={() =>
                      setDialog(
                        <ReasonDialog
                          title="Reject payment"
                          label="Reason (the payer sees this)"
                          button="Reject"
                          onClose={close}
                          onSave={(reason) => rejectPayment(p.id, reason).then(() => done("Payment rejected."))}
                          onFail={fail}
                        />,
                      )
                    }
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))
          ) : (
            <p style={{ color: "var(--muted)", margin: 0 }}>Nothing to verify.</p>
          )}
        </div>
        <div className="card">
          <h3>Refund requests ({openRefunds.length})</h3>
          {openRefunds.length ? (
            openRefunds.map((r) => (
              <div className="xrow" key={r.id}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <b>{r.name}</b>
                  <small>
                    {r.description} · {r.invoice_no ?? "no invoice (duplicate payment)"} · {r.reason}
                  </small>
                </div>
                <div className="cr" style={{ margin: 0, gap: 8 }}>
                  <b>{formatMoney(r.amount_poisha)}</b>
                  <button className="btn sm" type="button" onClick={() => setDialog(<ApproveRefundDialog refund={r} onClose={close} onDone={() => done("Refund approved.")} onFail={fail} />)}>
                    Approve
                  </button>
                  <button
                    className="btn ghost sm"
                    type="button"
                    onClick={() =>
                      setDialog(
                        <ReasonDialog
                          title="Decline refund"
                          label="Reason (the person sees this)"
                          button="Decline"
                          onClose={close}
                          onSave={(reason) => declineRefund(r.id, reason).then(() => done("Refund declined."))}
                          onFail={fail}
                        />,
                      )
                    }
                  >
                    Decline
                  </button>
                </div>
              </div>
            ))
          ) : (
            <p style={{ color: "var(--muted)", margin: 0 }}>No refund requests.</p>
          )}
        </div>
        <div className="card">
          <h3>Outstanding balances · {formatMoney(outstanding.total_poisha)}</h3>
          {outstanding.items.length ? (
            outstanding.items.map((o) => (
              <div className="xrow" key={o.ref_type + o.ref_id}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <b>{o.name}</b>
                  <small>
                    {o.purpose} · {o.status === "unpaid" ? "Unpaid" : "Waiting verification"}
                  </small>
                </div>
                <div className="cr" style={{ margin: 0, gap: 8 }}>
                  <b>{formatMoney(o.amount_poisha)}</b>
                  {o.status === "unpaid" ? (
                    <button className="btn ghost sm" type="button" onClick={() => void sendPaymentReminder(o.applicant_id).then(() => toast("Reminder sent."), fail)}>
                      Remind
                    </button>
                  ) : null}
                </div>
              </div>
            ))
          ) : (
            <p style={{ color: "var(--muted)", margin: 0 }}>Nothing outstanding.</p>
          )}
        </div>
      </div>

      <AddEntry onDone={() => done("Added to the ledger.")} onFail={fail} />

      <div className="top" style={{ alignItems: "center", flexWrap: "wrap" }}>
        <h3 style={{ fontSize: 22, margin: 0 }}>Ledger</h3>
        <div className="cr" style={{ margin: 0 }}>
          <div className="seg" style={{ minWidth: 260, margin: 0, gridTemplateColumns: "repeat(3,1fr)" }}>
            {(
              [
                ["all", "All"],
                ["in", "Money in"],
                ["out", "Money out"],
              ] as const
            ).map(([d, text]) => (
              <button key={d} type="button" role="tab" aria-selected={direction === d} onClick={() => (setPage(1), setDirection(d))}>
                {text}
              </button>
            ))}
          </div>
          <a className="btn ghost sm" href={ledgerCsvUrl(direction, period)} download>
            Export CSV
          </a>
        </div>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        {ledger.items.length ? (
          <>
            <div className="lg h">
              <span>Date</span>
              <span>From / to</span>
              <span>Category</span>
              <span style={{ textAlign: "right" }}>Amount</span>
            </div>
            {ledger.items.map((x) => {
              const isIn = x.direction === "in";
              return (
                <div className="lg" key={x.id}>
                  <span>{formatDate(x.date)}</span>
                  <div>
                    <b>{x.party}</b>
                    <small>
                      {x.description}
                      {x.email ? " · " + x.email : ""}
                    </small>
                  </div>
                  <div>
                    <span className={"bd " + (isIn ? "ok" : "no")}>{x.category_label}</span>
                    <small>
                      {x.method || "–"} · {x.ref}
                      {x.auto ? " · auto" : ""}
                      {x.reversed ? " · reversed by " + x.reversed_by : ""}
                    </small>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <b style={{ color: isIn ? GREEN : RED }}>
                      {isIn ? "+" : "−"}
                      {formatMoney(x.amount_poisha)}
                    </b>
                    <small>Balance {formatMoney(x.balance_poisha)}</small>
                    {!x.auto && !x.reversed && !x.reverses_ref ? (
                      <button
                        className="lk"
                        type="button"
                        onClick={() =>
                          setDialog(
                            <ReasonDialog
                              title={"Reverse " + x.ref}
                              label="Reason"
                              button="Reverse"
                              onClose={close}
                              onSave={(reason) => reverseLedgerEntry(x.id, reason).then(() => done("Entry reversed."))}
                              onFail={fail}
                            />,
                          )
                        }
                      >
                        Reverse
                      </button>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </>
        ) : (
          <p style={{ color: "var(--muted)", margin: 0 }}>No transactions yet. Fees from courses and applications appear here automatically.</p>
        )}
        {ledger.total > ledger.page_size ? (
          <div className="cr">
            <button className="btn ghost sm" type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Newer
            </button>
            <span style={{ color: "var(--muted)", fontSize: 14 }}>
              Page {page} of {Math.ceil(ledger.total / ledger.page_size)}
            </span>
            <button className="btn ghost sm" type="button" disabled={page * ledger.page_size >= ledger.total} onClick={() => setPage(page + 1)}>
              Older
            </button>
          </div>
        ) : null}
      </div>

      <div className="card" style={{ marginTop: 24 }}>
        <h3>Invoices</h3>
        <div className="flt" style={{ marginTop: 0 }}>
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search invoice number, name or email" aria-label="Search invoices" />
        </div>
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
            { head: "Module", cell: (i) => (i.module === "course" ? "Training" : i.module === "study" ? "Consultancy" : i.module === "visa" ? "Immigration" : "Jobs") },
            { head: "Amount", cell: (i) => formatMoney(i.amount_poisha) },
            { head: "Status", cell: (i) => (i.status === "refunded" ? <span className="bd no">Refunded</span> : <span className="bd ok">Paid</span>) },
            { head: "Email", cell: (i) => (i.email_status === "sent" ? "Sent" : i.email_status === "failed" ? "Failed" : "Queued") },
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
      {/* B16: finance has no Agents tab, so the agent commissions are shown here for finance. */}
      {admin?.role === "finance" && commissionSections.length ? (
        <>
          <h3 className="rh">Agent commissions</h3>
          <CommissionsPanel admin={admin} sections={commissionSections} toast={toast} onSignedOut={onSignedOut} />
        </>
      ) : null}
      <InvoiceDialog invoice={shownInvoice} open={shownInvoice !== null} onClose={() => setShownInvoice(null)} />
      {dialog}
    </TabPage>
  );
}

function AddEntry({ onDone, onFail }: { onDone: () => void; onFail: (err: unknown) => void }) {
  const [direction, setDirection] = useState<LedgerDirection>("out");
  const [category, setCategory] = useState(LEDGER_CATEGORIES.out[0].key);
  const [date, setDate] = useState(today());
  const [amount, setAmount] = useState("");
  const [party, setParty] = useState("");
  const [method, setMethod] = useState<string>(LEDGER_METHODS[4]);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    if (!/^\d+$/.test(amount.trim()) || Number(amount) <= 0) return setError("Please enter a whole amount above 0.");
    if (!party.trim()) return setError("Please fill in: Received from / paid to.");
    if (!date || date > today()) return setError("The date cannot be in the future.");
    setBusy(true);
    try {
      await addLedgerEntry({ direction, category, date, amount_poisha: Number(amount.trim()) * 100, party: party.trim(), email: "", method, note: note.trim() });
      setAmount("");
      setParty("");
      setNote("");
      setError("");
      onDone();
    } catch (err) {
      if (isApiError(err) && err.code === "VALIDATION") setError(err.message);
      else onFail(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <h3>Add an entry</h3>
      <p style={{ marginBottom: 14 }}>Course and application fees are recorded automatically. Add everything else here: expenses, cash received, opening balance.</p>
      <form noValidate onSubmit={(e) => void save(e)}>
        <div className="fgrid">
          <label className="fl">
            <span>Type</span>
            <select
              value={direction}
              onChange={(e) => {
                const d = e.target.value as LedgerDirection;
                setDirection(d);
                setCategory(LEDGER_CATEGORIES[d][0].key);
              }}
            >
              <option value="in">Money in</option>
              <option value="out">Money out</option>
            </select>
          </label>
          <label className="fl">
            <span>Category</span>
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              {LEDGER_CATEGORIES[direction]
                .filter((c) => !["course", "study", "job", "visa", "refund"].includes(c.key))
                .map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
            </select>
          </label>
          <label className="fl">
            <span>Date</span>
            <input type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} />
          </label>
          <TextField label="Amount (৳)" value={amount} onChange={setAmount} placeholder="e.g. 5000" />
          <TextField label="Received from / paid to" value={party} onChange={setParty} placeholder="Person or company" />
          <label className="fl">
            <span>Method</span>
            <select value={method} onChange={(e) => setMethod(e.target.value)}>
              {LEDGER_METHODS.map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
          </label>
          <TextField label="Note" value={note} onChange={setNote} placeholder="What was it for?" full />
        </div>
        <p className="err" role="alert">
          {error}
        </p>
        <button className="btn" type="submit" disabled={busy}>
          Add to ledger
        </button>
      </form>
    </div>
  );
}

function Confirm({ title, text, button, onClose, onYes }: { title: string; text: string; button: string; onClose: () => void; onYes: () => Promise<unknown> }) {
  const [busy, setBusy] = useState(false);
  return (
    <Modal open title={title} onClose={onClose}>
      <p>{text}</p>
      <div className="cr" style={{ margin: 0 }}>
        <button className="btn" type="button" disabled={busy} onClick={() => (setBusy(true), void onYes().finally(() => setBusy(false)))}>
          {button}
        </button>
        <button className="btn ghost" type="button" onClick={onClose}>
          Cancel
        </button>
      </div>
    </Modal>
  );
}

type ReasonProps = { title: string; label: string; button: string; onClose: () => void; onSave: (reason: string) => Promise<void>; onFail: (err: unknown) => void };

function ReasonDialog({ title, label, button, onClose, onSave, onFail }: ReasonProps) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    if (!reason.trim()) return setError("Please give a reason.");
    setBusy(true);
    try {
      await onSave(reason.trim());
    } catch (err) {
      if (isApiError(err) && err.code === "VALIDATION") setError(err.message);
      else onFail(err);
      setBusy(false);
    }
  }

  return (
    <Modal open title={title} onClose={onClose}>
      <form noValidate onSubmit={(e) => void save(e)}>
        <div className="fgrid">
          <TextField label={label} value={reason} onChange={setReason} area={3} required full />
        </div>
        <p className="err" role="alert">
          {error}
        </p>
        <div className="cr" style={{ margin: 0 }}>
          <button className="btn" type="submit" disabled={busy}>
            {button}
          </button>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ApproveRefundDialog({ refund, onClose, onDone, onFail }: { refund: Refund; onClose: () => void; onDone: () => void; onFail: (err: unknown) => void }) {
  const [method, setMethod] = useState<string>("bKash");
  const [ref, setRef] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    if (!ref.trim()) return setError("Please fill in: Refund reference.");
    setBusy(true);
    try {
      await approveRefund(refund.id, method, ref.trim());
      onDone();
    } catch (err) {
      if (isApiError(err) && err.code === "VALIDATION") setError(err.message);
      else onFail(err);
      setBusy(false);
    }
  }

  return (
    <Modal open title={"Approve refund · " + formatMoney(refund.amount_poisha)} onClose={onClose}>
      <p className="sub">
        {refund.name} · {refund.invoice_no ?? "duplicate payment"}
      </p>
      <form noValidate onSubmit={(e) => void save(e)}>
        <div className="fgrid">
          <label className="fl">
            <span>Refunded via</span>
            <select value={method} onChange={(e) => setMethod(e.target.value)}>
              {LEDGER_METHODS.map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
          </label>
          <TextField label="Refund reference" value={ref} onChange={setRef} required />
        </div>
        <p className="err" role="alert">
          {error}
        </p>
        <div className="cr" style={{ margin: 0 }}>
          <button className="btn" type="submit" disabled={busy}>
            Approve refund
          </button>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}
