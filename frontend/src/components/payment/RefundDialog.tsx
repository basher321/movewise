"use client";

import { useState, type FormEvent } from "react";
import { requestRefund, type Module } from "@/lib/api";
import { errorText } from "../auth/messages";
import Modal from "../Modal";

type RefundDialogProps = {
  module: Module;
  invoiceNo: string;
  onClose: () => void;
  onSent: () => void;
};

// "Request a refund" (formDlg() in the reference): one required reason.
export default function RefundDialog({ module, invoiceNo, onClose, onSent }: RefundDialogProps) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await requestRefund(module, invoiceNo, reason);
      onSent();
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <Modal open title="Request a refund" onClose={onClose}>
      <form noValidate onSubmit={submit}>
        <div className="fgrid">
          <label className="fl" style={{ gridColumn: "1/-1" }}>
            <span>Reason</span>
            <textarea name="reason" value={reason} onChange={(e) => setReason(e.target.value)} required autoFocus />
          </label>
        </div>
        <p className="err" role="alert">
          {error}
        </p>
        <div className="cr" style={{ margin: 0 }}>
          <button className="btn" type="submit" disabled={busy}>
            Send request
          </button>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}
