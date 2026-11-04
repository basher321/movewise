"use client";

import { useState, type FormEvent } from "react";
import { isApiError, verifyCertificate, type CertificateCheck } from "@/lib/api";

type Result = { valid: CertificateCheck } | { missing: string } | { error: string } | null;

// The certificate check on /verify (renderVerify() in the reference). Only approved certificates are valid.
export default function VerifyForm() {
  const [id, setId] = useState("");
  const [result, setResult] = useState<Result>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const q = id.trim();
    if (!q) {
      setResult(null);
      return;
    }
    setBusy(true);
    try {
      const check = await verifyCertificate(q);
      setResult(check.valid ? { valid: check } : { missing: q });
    } catch (error) {
      if (isApiError(error) && error.code === "NOT_FOUND") setResult({ missing: q });
      else setResult({ error: isApiError(error) ? error.message : "Something went wrong. Please try again." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form className="search" style={{ maxWidth: "none" }} onSubmit={submit}>
        <input name="q" value={id} onChange={(e) => setId(e.target.value)} placeholder="e.g. CERT-ABCD2345" aria-label="Certificate ID" />
        <button className="btn" type="submit" disabled={busy}>
          Verify
        </button>
      </form>
      {result && "valid" in result ? (
        <div className="banner ok" style={{ marginTop: 18 }} role="status">
          ✓ Valid certificate. {result.valid.name} completed {result.valid.course_title}
        </div>
      ) : result && "missing" in result ? (
        <div className="banner no" style={{ marginTop: 18 }} role="status">
          No approved certificate found with ID {result.missing}.
        </div>
      ) : result ? (
        <div className="banner no" style={{ marginTop: 18 }} role="status">
          {result.error}
        </div>
      ) : null}
    </>
  );
}
