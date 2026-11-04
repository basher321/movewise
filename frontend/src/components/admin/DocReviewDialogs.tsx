"use client";

import { useState, type FormEvent } from "react";
import { isApiError, rejectDocument, verifyDocument, type AppDocument } from "@/lib/api";
import Modal from "../Modal";
import { errorText } from "../auth/messages";
import { TextField } from "./Field";

// The Verify and Reject document dialogs of bindDocs() in the reference (spec F08), shared by admin screens.

type Props = {
  doc: AppDocument;
  onClose: () => void;
  onDone: () => void;
  onSignedOut: () => void;
};

export function VerifyDocDialog({ doc, onClose, onDone, onSignedOut }: Props) {
  const [expiry, setExpiry] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      await verifyDocument(doc.id, expiry || undefined);
      onDone();
    } catch (err) {
      if (isApiError(err) && err.code === "UNAUTHENTICATED") return onSignedOut();
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <Modal open title="Verify document" onClose={onClose}>
      <form noValidate onSubmit={(e) => void save(e)}>
        <div className="fgrid">
          <label className="fl" style={{ gridColumn: "1/-1" }}>
            <span>Expiry date (optional, e.g. passport or police clearance)</span>
            <input type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} />
          </label>
        </div>
        <p className="err" role="alert">
          {error}
        </p>
        <div className="cr" style={{ margin: 0 }}>
          <button className="btn" type="submit" disabled={busy}>
            Verify
          </button>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function RejectDocDialog({ doc, onClose, onDone, onSignedOut }: Props) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    if (!reason.trim()) return setError("Please fill in: Reason (the applicant sees this).");
    setBusy(true);
    try {
      await rejectDocument(doc.id, reason);
      onDone();
    } catch (err) {
      if (isApiError(err) && err.code === "UNAUTHENTICATED") return onSignedOut();
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <Modal open title="Reject document" onClose={onClose}>
      <form noValidate onSubmit={(e) => void save(e)}>
        <div className="fgrid">
          <TextField label="Reason (the applicant sees this)" value={reason} onChange={setReason} area={3} required full />
        </div>
        <p className="err" role="alert">
          {error}
        </p>
        <div className="cr" style={{ margin: 0 }}>
          <button className="btn" type="submit" disabled={busy}>
            Reject
          </button>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}
