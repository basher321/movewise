"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import {
  adminSignIn,
  adminSignUp,
  getSetupStatus,
  isApiError,
  superAdminSignIn,
  superAdminSignUp,
  type SetupStatus,
} from "@/lib/api";
import ForgotPasswordDialog from "./ForgotPasswordDialog";
import PasswordInput from "./PasswordInput";

const WAITING = "Your account is waiting for approval by the Super Admin.";

type AdminAuthProps = {
  onSignedIn: () => void;
  // "staff" on /admin, "super" on /super-admin (B14).
  variant?: "staff" | "super";
  // Super page only: a staff session is open, which cannot open the Super Admin panel.
  staffSignedIn?: boolean;
};

// Admin sign in / sign up card (admAuth() in the reference), for staff and for the Super Admin.
export default function AdminAuth({ onSignedIn, variant = "staff", staffSignedIn = false }: AdminAuthProps) {
  const isSuper = variant === "super";
  const [mode, setMode] = useState<"in" | "up">("in");
  const [message, setMessage] = useState<{ text: string; ok: boolean }>({ text: "", ok: false });
  const [busy, setBusy] = useState(false);
  const [forgot, setForgot] = useState(false);
  // Super page only: whether sign-up is open (no Super Admin yet) and needs the setup code.
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const canSignUp = !isSuper || (status !== null && !status.super_admin_exists);
  const up = mode === "up" && canSignUp;

  useEffect(() => {
    if (!isSuper) return;
    let alive = true;
    getSetupStatus()
      .then((s) => {
        if (alive) setStatus(s);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [isSuper]);

  function switchTo(next: "in" | "up") {
    setMode(next);
    setMessage({ text: "", ok: false });
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const name = String(form.get("nm") ?? "");
    const email = String(form.get("em") ?? "");
    const password = String(form.get("pw") ?? "");
    setBusy(true);
    try {
      if (up && isSuper) {
        await superAdminSignUp(name, email, password, status?.needs_setup ? String(form.get("sc") ?? "") : undefined);
        onSignedIn();
        return;
      }
      if (up) {
        await adminSignUp(name, email, password);
        setMode("in");
        setMessage({ text: WAITING, ok: true });
        return;
      }
      await (isSuper ? superAdminSignIn : adminSignIn)(email, password);
      onSignedIn();
    } catch (error) {
      const text = !isApiError(error)
        ? "Something went wrong. Please try again."
        : error.code === "UNAUTHENTICATED"
          ? "Wrong email or password."
          : error.code === "FORBIDDEN" && !up && !isSuper
            ? WAITING
            : error.message;
      setMessage({ text, ok: false });
    } finally {
      setBusy(false);
    }
  }

  const title = isSuper ? (up ? "Create Super Admin account" : "Super Admin sign in") : up ? "Create admin account" : "Admin sign in";
  const lead = isSuper
    ? up
      ? "First-time setup: create the Super Admin account. It has full access to the whole system."
      : "Sign in with the Super Admin account to open the Super Admin panel."
    : up
      ? "Staff accounts need approval from the Super Admin before they can sign in."
      : "Sign in to manage applications and accounts.";

  return (
    <section>
      <div className="wrap" style={{ maxWidth: 460 }}>
        <div className="card">
          <h2 style={{ fontSize: 28, marginBottom: 6 }}>{title}</h2>
          <p style={{ marginBottom: 18 }}>{lead}</p>
          {isSuper && staffSignedIn ? (
            <p className="err" role="status" style={{ marginBottom: 14 }}>
              You are signed in as staff. Sign in with the Super Admin account to open the Super Admin panel.
            </p>
          ) : null}
          {canSignUp ? (
            <div className="seg" role="tablist">
              <button type="button" role="tab" aria-selected={!up} onClick={() => switchTo("in")}>
                Sign in
              </button>
              <button type="button" role="tab" aria-selected={up} onClick={() => switchTo("up")}>
                Sign up
              </button>
            </div>
          ) : null}
          <form key={mode} noValidate onSubmit={submit}>
            {up ? <input name="nm" placeholder="Full name" aria-label="Full name" autoComplete="name" /> : null}
            <input name="em" type="email" placeholder="Email" aria-label="Email" autoComplete="email" />
            <PasswordInput
              name="pw"
              placeholder="Password (6+ characters)"
              aria-label="Password"
              autoComplete={up ? "new-password" : "current-password"}
            />
            {up && isSuper && status?.needs_setup ? (
              <input name="sc" placeholder="Setup code" aria-label="Setup code" autoComplete="off" />
            ) : null}
            <p className="err" role="alert" style={message.ok ? { color: "#16A34A" } : undefined}>
              {message.text}
            </p>
            <button className="btn" type="submit" style={{ justifyContent: "center" }} disabled={busy}>
              {up ? "Create account" : "Sign in"}
            </button>
            {up ? null : (
              <button className="lk" type="button" onClick={() => setForgot(true)} style={{ justifySelf: "center" }}>
                Forgot password?
              </button>
            )}
          </form>
          <p style={{ margin: "16px 0 0", fontSize: 14, textAlign: "center" }}>
            {isSuper ? (
              <>
                Staff member? <Link href="/admin" style={{ fontWeight: 600 }}>Use the staff sign in.</Link>
              </>
            ) : (
              <>
                Super Admin? <Link href="/super-admin" style={{ fontWeight: 600 }}>Use the Super Admin page.</Link>
              </>
            )}
          </p>
        </div>
      </div>
      {forgot ? <ForgotPasswordDialog variant={variant} onClose={() => setForgot(false)} /> : null}
    </section>
  );
}
