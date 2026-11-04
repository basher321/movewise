"use client";

import { useState, type FormEvent } from "react";
import { changeMyAdminPassword, updateMyAdminAccount, type AdminUser } from "@/lib/api";
import { errorText } from "../auth/messages";
import Modal from "../Modal";
import PasswordInput from "./PasswordInput";

type MyAccountDialogProps = {
  admin: AdminUser;
  onClose: () => void;
  // Called after the name or email was saved, so the panel shows the new details.
  onSaved: () => void;
  toast: (message: string, bad?: boolean) => void;
};

const full = { gridColumn: "1/-1" } as const;

// "My account" in the admin panel (B13): the staff member's own name, email and password.
export default function MyAccountDialog({ admin, onClose, onSaved, toast }: MyAccountDialogProps) {
  return (
    <Modal open title="My account" onClose={onClose}>
      <DetailsForm admin={admin} onSaved={onSaved} toast={toast} />
      <hr style={{ border: 0, borderTop: "1px solid var(--line)", margin: "22px 0" }} />
      <PasswordForm toast={toast} />
      <div className="cr" style={{ margin: "18px 0 0" }}>
        <button className="btn ghost" type="button" onClick={onClose}>
          Close
        </button>
      </div>
    </Modal>
  );
}

function DetailsForm({ admin, onSaved, toast }: Omit<MyAccountDialogProps, "onClose">) {
  const [name, setName] = useState(admin.name);
  const [email, setEmail] = useState(admin.email);
  const [current, setCurrent] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const emailChanged = email.trim().toLowerCase() !== admin.email.toLowerCase();

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await updateMyAdminAccount(name, email, emailChanged ? current : "");
      setCurrent("");
      toast("Your details were saved.");
      onSaved();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form noValidate onSubmit={submit}>
      <h3 style={{ fontSize: 18, marginBottom: 12 }}>Name and email</h3>
      <div className="fgrid">
        <label className="fl" style={full}>
          <span>Full name</span>
          <input name="name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required />
        </label>
        <label className="fl" style={full}>
          <span>Email (you sign in with it)</span>
          <input name="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
        </label>
        {emailChanged ? (
          <label className="fl" style={full}>
            <span>Current password (needed to change the email)</span>
            <PasswordInput name="currentPasswordForEmail" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" />
          </label>
        ) : null}
      </div>
      <p className="err" role="alert">
        {error}
      </p>
      <button className="btn" type="submit" disabled={busy}>
        Save details
      </button>
    </form>
  );
}

function PasswordForm({ toast }: Pick<MyAccountDialogProps, "toast">) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    if (next !== again) {
      setError("The two new passwords are not the same.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await changeMyAdminPassword(current, next);
      setCurrent("");
      setNext("");
      setAgain("");
      toast("Your password was changed.");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form noValidate onSubmit={submit}>
      <h3 style={{ fontSize: 18, marginBottom: 12 }}>Change password</h3>
      <div className="fgrid">
        <label className="fl" style={full}>
          <span>Current password</span>
          <PasswordInput name="currentPassword" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
        </label>
        <label className="fl" style={full}>
          <span>New password (6+ characters)</span>
          <PasswordInput name="newPassword" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required />
        </label>
        <label className="fl" style={full}>
          <span>New password again</span>
          <PasswordInput name="newPasswordAgain" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
        </label>
      </div>
      <p className="err" role="alert">
        {error}
      </p>
      <button className="btn" type="submit" disabled={busy}>
        Change password
      </button>
    </form>
  );
}
