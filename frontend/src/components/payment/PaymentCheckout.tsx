"use client";

import { useRef, useState, type FormEvent } from "react";
import type { PaymentMethod, PayStart } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { useSettings } from "../SettingsProvider";
import { enabledMethods, METHOD_NAMES } from "./methods";

type PaymentCheckoutProps = {
  amount_poisha: number;
  // What is being paid for; read out to screen readers.
  purpose: string;
  // Starts the payment and returns what the api says. Errors thrown here are shown in the error line.
  onPay: (method: PaymentMethod, manualRef?: string) => Promise<PayStart>;
  // Runs for a bank / office payment, which waits for finance to verify it.
  onDone: (result: PayStart) => void;
};

// The checkout part of a payment dialog (section 5 "PAYMENTS" in the reference): methods from Settings,
// the receipt number for manual payments, the error line and the pay button. For SSLCommerz and
// bKash the browser goes to the gateway; the payment result page shows the outcome after the
// server has checked it with the gateway. This form never decides that a payment succeeded.
export default function PaymentCheckout({ amount_poisha, purpose, onPay, onDone }: PaymentCheckoutProps) {
  const { settings } = useSettings();
  const methods = enabledMethods(settings);
  const [chosen, setChosen] = useState<PaymentMethod | null>(null);
  const method = chosen && methods.includes(chosen) ? chosen : (methods[0] ?? null);
  const [receipt, setReceipt] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const running = useRef(false);
  const receiptRef = useRef<HTMLInputElement>(null);
  const manual = method === "manual";

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!method || running.current) return;
    setError("");
    if (manual && !receipt.trim()) {
      setError("Please enter your receipt / transaction number.");
      receiptRef.current?.focus();
      return;
    }
    running.current = true;
    setBusy(true);
    try {
      const result = await onPay(method, manual ? receipt.trim() : undefined);
      if (result.redirect_url) {
        // Keep the button busy while the browser leaves for the gateway.
        window.location.assign(result.redirect_url);
        return;
      }
      running.current = false;
      setBusy(false);
      onDone(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
      running.current = false;
      setBusy(false);
    }
  }

  if (!method) {
    return (
      <p className="err" role="alert">
        No payment method is set up yet. Please contact us.
      </p>
    );
  }

  const label = busy && !manual ? "Connecting to " + METHOD_NAMES[method] + "…" : manual ? "Submit for verification" : "Pay " + formatMoney(amount_poisha);

  return (
    <form noValidate onSubmit={submit} aria-label={purpose}>
      <select
        aria-label="Payment method"
        value={method}
        onChange={(e) => {
          setChosen(e.target.value as PaymentMethod);
          setError("");
        }}
      >
        {methods.map((m) => (
          <option key={m} value={m}>
            {METHOD_NAMES[m]}
          </option>
        ))}
      </select>
      {manual ? (
        <>
          <input
            ref={receiptRef}
            name="mref"
            value={receipt}
            onChange={(e) => setReceipt(e.target.value)}
            placeholder="Receipt / transaction number"
            aria-label="Receipt or transaction number"
          />
          <p className="sub" style={{ margin: 0, fontSize: 13 }}>
            {settings?.gateways.manual.instructions}
          </p>
        </>
      ) : (
        <p className="sub" style={{ margin: 0, fontSize: 13 }}>
          You will pay on the secure {METHOD_NAMES[method]} page and then come back here.
        </p>
      )}
      <p className="err" role="alert">
        {error}
      </p>
      <button className="btn" type="submit" disabled={busy} style={{ justifyContent: "center" }}>
        {label}
      </button>
    </form>
  );
}
