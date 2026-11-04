"use client";

import { useState, type FormEvent } from "react";
import { updateMyProfile, type ApplicantAccount } from "@/lib/api";
import { errorText } from "../auth/messages";
import Modal from "../Modal";

type EditDetailsDialogProps = {
  account: ApplicantAccount;
  onClose: () => void;
  onSaved: () => Promise<void>;
};

// "Edit details" on the profile, in the style of formDlg() in the reference.
export default function EditDetailsDialog({ account, onClose, onSaved }: EditDetailsDialogProps) {
  const [form, setForm] = useState({
    name: account.name,
    phone: account.phone,
    email: account.email ?? "",
    country: account.country,
    education: account.education,
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const field = (key: keyof typeof form) => ({
    name: key,
    value: form[key],
    onChange: (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value }),
  });

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await updateMyProfile(account.module, form);
      await onSaved();
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <Modal open title="Edit details" onClose={onClose}>
      <form noValidate onSubmit={submit}>
        <div className="fgrid">
          <label className="fl">
            <span>Full name</span>
            <input {...field("name")} autoComplete="name" required autoFocus />
          </label>
          <label className="fl">
            <span>Phone</span>
            <input {...field("phone")} type="tel" autoComplete="tel" placeholder={account.username ? "Optional" : undefined} />
          </label>
          <label className="fl">
            <span>Email{account.username ? " (optional)" : ""}</span>
            <input {...field("email")} type="email" autoComplete="email" />
          </label>
          <label className="fl">
            <span>Country</span>
            <input {...field("country")} autoComplete="country-name" />
          </label>
          <label className="fl">
            <span>Education / work</span>
            <input {...field("education")} />
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
