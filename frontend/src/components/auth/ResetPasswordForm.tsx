"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { resetPassword, type ResetKind } from "@/lib/api";
import PasswordInput from "../admin/PasswordInput";
import { errorText } from "./messages";

const SIGN_IN: Record<ResetKind, { href: string; label: string }> = {
  admin: { href: "/admin", label: "Go to staff sign in" },
  course: { href: "/courses", label: "Go to Courses and sign in" },
  study: { href: "/consultancy", label: "Go to Student Consultancy and sign in" },
  job: { href: "/jobs", label: "Go to Job Processing and sign in" },
  visa: { href: "/immigration", label: "Go to Immigration Processing and sign in" },
};

// /reset-password?token=... (B15): the page the "Forgot password?" email links to.
export default function ResetPasswordForm() {
  const token = useSearchParams().get("token") ?? "";
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<ResetKind | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    if (next.length < 6) return setError("Password must be at least 6 characters.");
    if (next !== again) return setError("The two new passwords are not the same.");
    setBusy(true);
    setError("");
    try {
      const result = await resetPassword(token, next);
      setDone(result.kind);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return <p>This link is missing its code. Please open the link from the email again, or use &quot;Forgot password?&quot; once more.</p>;
  }

  if (done) {
    const to = SIGN_IN[done];
    return (
      <div className="card">
        <p style={{ marginBottom: 14 }}>Your password was changed. You can sign in with the new password now.</p>
        <Link className="btn" href={to.href}>
          {to.label}
        </Link>
        {done === "admin" ? (
          <p style={{ margin: "12px 0 0", fontSize: 14 }}>
            Super Admin? <Link href="/super-admin" style={{ fontWeight: 600 }}>Use the Super Admin page.</Link>
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="card">
      <form noValidate onSubmit={submit}>
        <PasswordInput name="newPassword" placeholder="New password (6+ characters)" aria-label="New password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} autoFocus />
        <PasswordInput name="newPasswordAgain" placeholder="New password again" aria-label="New password again" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} />
        <p className="err" role="alert">
          {error}
        </p>
        <button className="btn" type="submit" style={{ justifyContent: "center" }} disabled={busy}>
          Save new password
        </button>
      </form>
    </div>
  );
}
