"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  cancelPaymentRequest,
  createPaymentRequest,
  isApiError,
  listPaymentRequests,
  myPaymentRequests,
  payOwnAmount,
  payPaymentRequest,
  type Module,
  type PaymentMethod,
  type PaymentRequest,
  type PayStart,
} from "@/lib/api";
import { parseCustomAmount } from "@/lib/customAmount";
import { formatDate, formatMoney } from "@/lib/format";
import type { ShowToast } from "../admin/Toast";
import { errorText } from "../auth/messages";
import Modal from "../Modal";
import PaymentCheckout from "./PaymentCheckout";

// B27: custom payments of any amount on a case or course enrolment, on top of the normal fee.
// The normal fee (application fee / course price) is paid exactly as before.

export type PayableCase = { id: string; ref: string; title: string };

function statusBadge(r: PaymentRequest): [string, string] {
  if (r.status === "paid") return ["Paid", "bd ok"];
  if (r.status === "cancelled") return ["Cancelled", "bd"];
  if (r.payment?.status === "pending_verify") return ["Waiting for verification", "bd warn"];
  return ["Due", "bd in"];
}

function RequestLine({ r, children }: { r: PaymentRequest; children?: React.ReactNode }) {
  const [label, cls] = statusBadge(r);
  return (
    <div style={{ borderTop: "1px solid var(--line)", padding: "10px 0", display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
      <div style={{ minWidth: 0, flex: "1 1 220px" }}>
        <b style={{ display: "block", overflowWrap: "anywhere" }}>{r.description}</b>
        <small style={{ color: "var(--muted)" }}>
          {r.ref} · {r.case_ref} · {r.kind === "own" ? "your own amount" : "requested"} · {formatDate(r.created_at)}
          {r.invoice_no ? " · invoice " + r.invoice_no : ""}
        </small>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <b style={{ font: "700 17px var(--font-sora)" }}>{formatMoney(r.amount_poisha)}</b>
        <span className={cls} style={{ margin: 0 }}>
          {label}
        </span>
        {children}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- applicant

type MyProps = { module: Module; cases: PayableCase[]; phone: string; toast: ShowToast };

// The "Payments" block of the profile: payments due (asked for by staff) and "Pay another amount".
export function MyCustomPayments({ module, cases, phone, toast }: MyProps) {
  const [items, setItems] = useState<PaymentRequest[] | null>(null);
  const [paying, setPaying] = useState<PaymentRequest | null>(null);
  const [own, setOwn] = useState(false);

  const load = useCallback(() => {
    void myPaymentRequests(module)
      .then((d) => setItems(d.items))
      .catch(() => setItems([]));
  }, [module]);

  useEffect(() => load(), [load]);

  if (!items || (!cases.length && !items.length)) return null;
  const due = items.filter((r) => r.status === "open" && r.kind === "requested");
  const history = items.filter((r) => !(r.status === "open" && r.kind === "requested"));

  function done(result: PayStart) {
    setPaying(null);
    setOwn(false);
    if (result.status === "pending_verify") toast("Payment submitted. We will verify it soon.");
    load();
  }

  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <div className="top" style={{ alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        <h3 style={{ margin: 0 }}>Payments due</h3>
        {cases.length ? (
          <button className="btn sm" type="button" onClick={() => setOwn(true)}>
            Pay another amount
          </button>
        ) : null}
      </div>
      {due.length ? (
        due.map((r) => (
          <RequestLine r={r} key={r.id}>
            {r.payment?.status === "pending_verify" ? null : (
              <button className="btn sm" type="button" onClick={() => setPaying(r)}>
                Pay
              </button>
            )}
          </RequestLine>
        ))
      ) : (
        <p className="sub" style={{ margin: "8px 0 0" }}>
          {cases.length ? "Nothing to pay right now. You can still pay another amount, for example a deposit or an instalment." : "Nothing to pay right now."}
        </p>
      )}
      {history.length ? (
        <details style={{ marginTop: 10 }}>
          <summary style={{ cursor: "pointer", fontSize: 14, fontWeight: 600 }}>Other payments ({history.length})</summary>
          {history.map((r) => (
            <RequestLine r={r} key={r.id} />
          ))}
        </details>
      ) : null}
      {paying ? <PayRequestDialog module={module} request={paying} phone={phone} onClose={() => setPaying(null)} onDone={done} /> : null}
      {own ? <OwnAmountDialog module={module} cases={cases} phone={phone} onClose={() => setOwn(false)} onDone={done} /> : null}
    </div>
  );
}

function PhoneInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <input
      name="phone"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder="Your mobile number (01XXXXXXXXX)"
      aria-label="Mobile number"
      inputMode="tel"
      autoComplete="tel"
      style={{ marginBottom: 14 }}
    />
  );
}

function PayRequestDialog({
  module,
  request,
  phone: initialPhone,
  onClose,
  onDone,
}: {
  module: Module;
  request: PaymentRequest;
  phone: string;
  onClose: () => void;
  onDone: (r: PayStart) => void;
}) {
  const [phone, setPhone] = useState(initialPhone);
  const pay = (method: PaymentMethod, manualRef?: string) => payPaymentRequest(module, request.id, { method, phone, manual_ref: manualRef });
  return (
    <Modal open title="Pay" onClose={onClose}>
      <p className="sub">
        {request.ref} · {request.case_ref}
      </p>
      <div className="card" style={{ marginBottom: 16, padding: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span style={{ color: "var(--muted)", fontWeight: 600, overflowWrap: "anywhere" }}>{request.description}</span>
          <b style={{ font: "700 26px var(--font-sora)" }}>{formatMoney(request.amount_poisha)}</b>
        </div>
      </div>
      <PhoneInput value={phone} onChange={setPhone} />
      <PaymentCheckout amount_poisha={request.amount_poisha} purpose={request.description} onPay={pay} onDone={onDone} />
    </Modal>
  );
}

function OwnAmountDialog({
  module,
  cases,
  phone: initialPhone,
  onClose,
  onDone,
}: {
  module: Module;
  cases: PayableCase[];
  phone: string;
  onClose: () => void;
  onDone: (r: PayStart) => void;
}) {
  const [caseId, setCaseId] = useState(cases[0]?.id ?? "");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [phone, setPhone] = useState(initialPhone);
  const parsed = parseCustomAmount(amount);
  const poisha = "poisha" in parsed ? parsed.poisha : 0;

  function pay(method: PaymentMethod, manualRef?: string): Promise<PayStart> {
    if ("error" in parsed) return Promise.reject(new Error(parsed.error));
    return payOwnAmount(module, { case_id: caseId, amount_poisha: parsed.poisha, note: note.trim(), method, phone, manual_ref: manualRef });
  }

  return (
    <Modal open title="Pay another amount" onClose={onClose}>
      <p className="sub">Pay any amount towards your case, for example a deposit or an instalment. You get an invoice for it.</p>
      <div className="fgrid" style={{ marginBottom: 14 }}>
        {cases.length > 1 ? (
          <label className="fl">
            <span>For</span>
            <select value={caseId} onChange={(e) => setCaseId(e.target.value)}>
              {cases.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title} ({c.ref})
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className="fl">
          <span>Amount (৳)</span>
          <input inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="e.g. 5000" aria-label="Amount in taka" />
        </label>
        <label className="fl">
          <span>What is it for? (optional)</span>
          <input value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} placeholder="e.g. First instalment" />
        </label>
      </div>
      {cases.length === 1 ? (
        <p className="sub" style={{ marginTop: 0 }}>
          For {cases[0].title} ({cases[0].ref})
        </p>
      ) : null}
      {amount.trim() && "error" in parsed ? (
        <p className="err" role="alert" style={{ marginTop: 0 }}>
          {parsed.error}
        </p>
      ) : null}
      <PhoneInput value={phone} onChange={setPhone} />
      <PaymentCheckout amount_poisha={poisha} purpose="Pay another amount" onPay={pay} onDone={onDone} />
    </Modal>
  );
}

// ---------------------------------------------------------------- staff

type StaffProps = { module: Module; caseId: string; toast: ShowToast; onSignedOut: () => void };

// The "Custom payments" block of a case card or course enrolment card (super admin, or an admin
// of that section): the list, "Request a payment" and Cancel on open requests.
export function StaffCustomPayments({ module, caseId, toast, onSignedOut }: StaffProps) {
  const [items, setItems] = useState<PaymentRequest[] | null>(null);
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const fail = useCallback(
    (err: unknown) => {
      if (isApiError(err) && err.code === "UNAUTHENTICATED") onSignedOut();
      else setError(errorText(err));
    },
    [onSignedOut],
  );

  const [opened, setOpened] = useState(false);

  const load = useCallback(() => {
    void listPaymentRequests(module, caseId)
      .then((d) => setItems(d.items))
      .catch(fail);
  }, [module, caseId, fail]);

  useEffect(() => {
    if (opened) load();
  }, [opened, load]);

  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    if (!description.trim()) return setError("Please write what the payment is for.");
    const parsed = parseCustomAmount(amount);
    if ("error" in parsed) return setError(parsed.error);
    setBusy(true);
    try {
      await createPaymentRequest({ module, case_id: caseId, description: description.trim(), amount_poisha: parsed.poisha });
      setDescription("");
      setAmount("");
      setError("");
      toast("Payment requested. The applicant has been told.");
      load();
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function cancel(r: PaymentRequest) {
    if (busy) return;
    setBusy(true);
    try {
      await cancelPaymentRequest(r.id);
      setError("");
      toast("Payment request cancelled.");
      load();
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <details
      style={{ marginTop: 16, borderTop: "1px solid var(--line)", paddingTop: 14 }}
      onToggle={(e) => setOpened((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary style={{ cursor: "pointer", fontSize: 14, fontWeight: 600 }}>Custom payments</summary>
      <small style={{ display: "block", color: "var(--muted)" }}>
        Extra payments on top of the normal fee. The applicant pays them under Payments due in their profile, and can also pay an amount of their own.
      </small>
      {items?.map((r) => (
        <RequestLine r={r} key={r.id}>
          {r.status === "open" && r.kind === "requested" && r.payment?.status !== "pending_verify" ? (
            <button className="btn ghost sm" type="button" disabled={busy} onClick={() => void cancel(r)}>
              Cancel
            </button>
          ) : null}
        </RequestLine>
      ))}
      <form noValidate onSubmit={(e) => void add(e)} style={{ marginTop: 10 }}>
        <div className="fgrid">
          <label className="fl">
            <span>Payment for</span>
            <input value={description} maxLength={200} onChange={(e) => setDescription(e.target.value)} placeholder="e.g. Visa processing fee" />
          </label>
          <label className="fl">
            <span>Amount (৳)</span>
            <input inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="e.g. 25000" />
          </label>
        </div>
        <p className="err" role="alert">
          {error}
        </p>
        <div className="cr" style={{ marginTop: 0 }}>
          <button className="btn sm" type="submit" disabled={busy}>
            Request payment
          </button>
        </div>
      </form>
    </details>
  );
}
