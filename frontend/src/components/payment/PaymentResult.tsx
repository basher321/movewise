"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getMyInvoice, getMyPayment, isApiError, NETWORK_MESSAGE, type Invoice, type PaymentResult as Payment } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import InvoiceDialog from "./InvoiceDialog";
import { METHOD_NAMES } from "./methods";

const POLL_MS = 3000;
const MAX_MS = 60000;

// /payment/result?id=<payment id>: where SSLCommerz and bKash send the payer back.
// The page only shows what the server has confirmed with the gateway; it asks again every
// 3 seconds for up to a minute while the payment is still being confirmed.
export default function PaymentResult() {
  const id = useSearchParams().get("id") ?? "";
  const [payment, setPayment] = useState<Payment | null>(null);
  const [error, setError] = useState("");
  const [timedOut, setTimedOut] = useState(false);
  const [invoice, setInvoice] = useState<Invoice | null>(null);

  useEffect(() => {
    if (!id) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const started = Date.now();

    async function check() {
      try {
        const p = await getMyPayment(id);
        if (!live) return;
        setPayment(p);
        setError("");
        if (p.status === "initiated") {
          if (Date.now() - started < MAX_MS) timer = setTimeout(() => void check(), POLL_MS);
          else setTimedOut(true);
        }
      } catch (err) {
        if (!live) return;
        if (isApiError(err) && err.code === "UNAUTHENTICATED") setError("Please sign in to see your payment.");
        else if (isApiError(err) && err.code === "NOT_FOUND") setError("We could not find this payment.");
        else setError(isApiError(err) ? err.message : NETWORK_MESSAGE);
      }
    }

    void check();
    return () => {
      live = false;
      if (timer) clearTimeout(timer);
    };
  }, [id]);

  async function openInvoice() {
    if (!payment?.invoice_no) return;
    try {
      setInvoice(await getMyInvoice(payment.module, payment.invoice_no));
    } catch {
      setError("The invoice could not be opened. You can find it in your profile.");
    }
  }

  const profile = payment ? "/profile/" + payment.module : "/";

  if (!id) return <div className="banner no">This link is missing the payment reference.</div>;
  if (error) {
    return (
      <div className="card">
        <div className="banner no" style={{ margin: 0 }}>
          {error}
        </div>
        <div className="cr">
          <Link className="btn ghost sm" href="/">
            Back to the website
          </Link>
        </div>
      </div>
    );
  }
  if (!payment) return <p style={{ color: "var(--muted)" }}>Loading…</p>;

  const amount = formatMoney(payment.amount_poisha);
  let title: string;
  let body: string;
  let tone: "ok" | "in" | "no";
  switch (payment.status) {
    case "paid":
      [title, body, tone] = ["Payment received ✓", amount + " for " + payment.purpose + " is paid. Your invoice " + payment.invoice_no + " is ready.", "ok"];
      break;
    case "pending_verify":
      [title, body, tone] = [
        "Waiting for verification",
        amount + " for " + payment.purpose + " is waiting for our finance team. " + (payment.note ? payment.note + ". " : "") + "We will email you when it is confirmed.",
        "in",
      ];
      break;
    case "initiated":
      [title, body, tone] = timedOut
        ? ["Still confirming…", "The payment gateway has not confirmed your payment yet. If money was taken, it will be confirmed automatically; please check your profile in a few minutes.", "in"]
        : ["Confirming your payment…", "Please wait a moment while we check with " + METHOD_NAMES[payment.method] + ".", "in"];
      break;
    case "cancelled":
      [title, body, tone] = ["Payment cancelled", "No money was taken. You can try again from your profile.", "no"];
      break;
    case "refunded":
      [title, body, tone] = ["Payment refunded", amount + " was refunded.", "in"];
      break;
    case "duplicate":
      [title, body, tone] = ["Already paid", "This fee was already paid, so this payment will be refunded to you. Our finance team has been told.", "in"];
      break;
    default:
      [title, body, tone] = ["Payment not completed", "The payment did not go through. If money was taken, contact us with this reference: " + payment.id + ". Otherwise you can try again.", "no"];
  }

  return (
    <div className="card">
      <h3>{title}</h3>
      <div className={"banner " + tone} style={{ margin: "0 0 14px" }} role="status" aria-live="polite">
        {body}
      </div>
      <div className="cr" style={{ margin: 0 }}>
        {payment.status === "paid" && payment.invoice_no ? (
          <button className="btn" type="button" onClick={() => void openInvoice()}>
            View invoice
          </button>
        ) : null}
        {payment.status === "failed" || payment.status === "cancelled" || payment.status === "rejected" || payment.status === "abandoned" ? (
          <Link className="btn" href={profile}>
            Try again
          </Link>
        ) : null}
        <Link className="btn ghost" href={profile}>
          Go to my profile
        </Link>
      </div>
      <InvoiceDialog invoice={invoice} open={invoice !== null} onClose={() => setInvoice(null)} />
    </div>
  );
}
