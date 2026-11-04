"use client";

import { useEffect, useState, type FormEvent } from "react";
import { forgotPassword, getPasswordOptions } from "@/lib/api";
import { errorText, LINK_SENT } from "../auth/messages";
import Modal from "../Modal";

// "Forgot password?" on /admin and /super-admin (B15): an email link when email is set up,
// otherwise who can reset the password.
export default function ForgotPasswordDialog({ variant, onClose }: { variant: "staff" | "super"; onClose: () => void }) {
  const [email, setEmail] = useState<boolean | null>(null);
  const [login, setLogin] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    getPasswordOptions()
      .then((o) => {
        if (alive) setEmail(o.email);
      })
      .catch(() => {
        if (alive) setEmail(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    if (!login.trim()) return setError("Please enter your email.");
    setBusy(true);
    setError("");
    try {
      await forgotPassword("admin", login);
      setSent(true);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const ask =
    variant === "super"
      ? "Ask another Super Admin to reset your password in the Team tab. If there is none, the person who runs the server can set a new one with tools/admin/set_password.py."
      : "Ask a Super Admin to reset your password in the Team tab. They will give you a temporary password.";

  return (
    <Modal open title="Forgot your password?" onClose={onClose}>
      {email === null ? null : sent ? (
        <p>{LINK_SENT}</p>
      ) : email ? (
        <form noValidate onSubmit={submit}>
          <p>Enter the email you sign in with. We will email you a link to choose a new password.</p>
          <input name="forgotEmail" type="email" placeholder="Email" aria-label="Email" autoComplete="email" value={login} onChange={(e) => setLogin(e.target.value)} autoFocus />
          <p className="err" role="alert">
            {error}
          </p>
          <button className="btn" type="submit" style={{ justifyContent: "center" }} disabled={busy}>
            Send reset link
          </button>
          <p className="sub" style={{ marginTop: 12 }}>
            No email? {ask}
          </p>
        </form>
      ) : (
        <p>{ask}</p>
      )}
      <div className="cr" style={{ margin: "14px 0 0" }}>
        <button className="btn ghost" type="button" onClick={onClose}>
          Close
        </button>
      </div>
    </Modal>
  );
}
