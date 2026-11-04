"use client";

import { useState, type FormEvent } from "react";
import { changeMyPassword, type Module } from "@/lib/api";
import { errorText } from "../auth/messages";
import Modal from "../Modal";

type ChangePasswordDialogProps = {
  module: Module;
  onClose: () => void;
  onChanged: () => void;
};

// "Change password" on the profile, in the style of formDlg() in the reference.
export default function ChangePasswordDialog({ module, onClose, onChanged }: ChangePasswordDialogProps) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await changeMyPassword(module, current, next);
      onChanged();
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <Modal open title="Change password" onClose={onClose}>
      <form noValidate onSubmit={submit}>
        <div className="fgrid">
          <label className="fl" style={{ gridColumn: "1/-1" }}>
            <span>Current password</span>
            <input name="currentPassword" type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required autoFocus />
          </label>
          <label className="fl" style={{ gridColumn: "1/-1" }}>
            <span>New password (6+ characters)</span>
            <input name="newPassword" type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required />
          </label>
        </div>
        <p className="err" role="alert">
          {error}
        </p>
        <div className="cr" style={{ margin: 0 }}>
          <button className="btn" type="submit" disabled={busy}>
            Save
          </button>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}
