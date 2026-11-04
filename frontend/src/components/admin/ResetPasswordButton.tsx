"use client";

import { useState } from "react";
import { resetApplicantPassword } from "@/lib/api";
import Modal from "../Modal";
import { errorText } from "../auth/messages";

// "Reset password" for a person who forgot theirs (owner decision 2026-11-01: no email codes).
// The temporary password is shown once; staff give it to the person, who changes it in their profile.
export default function ResetPasswordButton({ accountId, name }: { accountId: string; name: string }) {
  const [result, setResult] = useState<{ password: string; username: string } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function reset() {
    if (!window.confirm("Set a new temporary password for " + name + "? Their current password stops working at once.")) return;
    setBusy(true);
    setError("");
    try {
      const r = await resetApplicantPassword(accountId);
      setResult({ password: r.temporary_password, username: r.username });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className="lk" type="button" disabled={busy} onClick={() => void reset()}>
        Reset password
      </button>
      {error ? <small style={{ color: "#DC2626" }}>{error}</small> : null}
      {result ? (
        <Modal open title="New temporary password" onClose={() => setResult(null)}>
          <p>Give these to {name} (by phone or in person). Ask them to change the password in their profile after signing in.</p>
          <div className="kv">
            {result.username ? (
              <div>
                <span>Username</span>
                <b>{result.username}</b>
              </div>
            ) : null}
            <div>
              <span>Temporary password</span>
              <b style={{ fontFamily: "monospace", fontSize: 18 }}>{result.password}</b>
            </div>
          </div>
          <p className="sub" style={{ marginTop: 12 }}>
            This password is shown only now.
          </p>
          <div className="cr" style={{ margin: 0 }}>
            <button className="btn" type="button" onClick={() => setResult(null)}>
              Done
            </button>
          </div>
        </Modal>
      ) : null}
    </>
  );
}
