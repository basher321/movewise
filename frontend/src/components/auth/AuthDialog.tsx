"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { applicantSignIn, applicantSignUp, forgotPassword, getPasswordOptions, isApiError, MODULES, type Module } from "@/lib/api";
import Modal from "../Modal";
import type { AuthRequest } from "../SessionProvider";
import { useSettings } from "../SettingsProvider";
import { authMessage, errorText, LINK_SENT } from "./messages";
import { accentColour, MODULE_UI, pageModule } from "./modules";

type Step = "form" | "forgot";
type Mode = "in" | "up";

type AuthDialogProps = {
  request: AuthRequest;
  onClose: () => void;
  onSignedIn: () => Promise<void>;
};

// The Sign in / Sign up dialog (#auth in the reference). Owner decision (2026-11-01): a username
// and password, signed in at once, no email code. Email and mobile are optional. A forgotten
// password is reset by our staff, so "Forgot password?" shows how to contact the office.
// B15 (2026-11-02): when email is set up, "Forgot password?" can also email a reset link.
export default function AuthDialog({ request, onClose, onSignedIn }: AuthDialogProps) {
  const pathname = usePathname();
  const { settings, licence } = useSettings();
  const licensed = MODULES.filter((m) => !!licence?.modules[m]);
  const [module, setModule] = useState<Module>(() => {
    const wanted = [request.module, pageModule(pathname)].find((m): m is Module => !!m && licensed.includes(m));
    return wanted ?? licensed[0] ?? "course";
  });
  const [step, setStep] = useState<Step>("form");
  const [mode, setMode] = useState<Mode>(request.mode);
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState(request.note ?? "");
  const [busy, setBusy] = useState(false);
  const running = useRef(false);
  // B15: whether a reset link can be emailed, and whether one was asked for.
  const [canEmail, setCanEmail] = useState(false);
  const [forgotLogin, setForgotLogin] = useState("");
  const [linkSent, setLinkSent] = useState(false);

  useEffect(() => {
    if (step !== "forgot") return;
    let alive = true;
    getPasswordOptions()
      .then((o) => {
        if (alive) setCanEmail(o.email);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [step]);

  function sendLink(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void run(async () => {
      setError("");
      if (!forgotLogin.trim()) return setError("Please enter your username or email.");
      try {
        await forgotPassword(module, forgotLogin);
        setLinkSent(true);
      } catch (err) {
        setError(errorText(err));
      }
    });
  }
  const ui = MODULE_UI[module];

  // One request at a time, so a quick double click sends it once.
  async function run(work: () => Promise<void>) {
    if (running.current) return;
    running.current = true;
    setBusy(true);
    try {
      await work();
    } finally {
      running.current = false;
      setBusy(false);
    }
  }

  function chooseModule(m: Module) {
    setModule(m);
    setError("");
    setNote("");
  }

  function chooseMode(m: Mode) {
    setMode(m);
    setError("");
    setNote("");
  }

  function submitForm(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void run(async () => {
      setError("");
      if (mode === "up" && !name.trim()) return setError("Please enter your full name.");
      if (!username.trim()) return setError(mode === "up" ? "Please choose a username." : "Please enter your username.");
      if (password.length < 6) return setError("Password must be at least 6 characters.");
      try {
        if (mode === "up") await applicantSignUp(module, { name, username, password, email, phone });
        else await applicantSignIn(module, username, password);
        await onSignedIn();
      } catch (err) {
        // An email that already has an account: that person should sign in instead.
        if (mode === "up" && isApiError(err) && err.code === "CONFLICT" && /email/i.test(err.message)) {
          setMode("in");
          setNote("");
        }
        setError(authMessage(err, mode));
      }
    });
  }

  const accent = accentColour(module, settings);

  if (step === "forgot") {
    const contact = [settings?.phone, settings?.email].filter(Boolean).join(" · ");
    return (
      <Modal open title="Forgot your password?" accent={accent} onClose={onClose}>
        {linkSent ? (
          <p>{LINK_SENT}</p>
        ) : canEmail ? (
          <form noValidate onSubmit={sendLink} style={{ marginBottom: 18 }}>
            <p>Enter your {ui.name} username or email. If your account has an email, we will send you a link to choose a new password.</p>
            <input
              name="forgotLogin"
              placeholder="Username or email"
              aria-label="Username or email"
              autoComplete="username"
              value={forgotLogin}
              onChange={(e) => setForgotLogin(e.target.value)}
            />
            <p className="err" role="alert">
              {error}
            </p>
            <button className="btn" type="submit" disabled={busy}>
              Send reset link
            </button>
          </form>
        ) : null}
        <p>
          {canEmail ? "No email on your account? " : ""}Please contact our office with your name and username. We will check who you are and give you a new password for your {ui.name}{" "}
          account.
        </p>
        {contact ? (
          <p>
            <b>{contact}</b>
            {settings?.hours ? <small style={{ display: "block", color: "var(--muted)" }}>{settings.hours}</small> : null}
          </p>
        ) : null}
        <div className="cr" style={{ margin: 0 }}>
          <button className="btn" type="button" onClick={() => setStep("form")}>
            Back to sign in
          </button>
        </div>
      </Modal>
    );
  }

  const up = mode === "up";
  return (
    <Modal open title={up ? "Create your " + ui.name + " account" : "Sign in to " + ui.name} accent={accent} onClose={onClose}>
      <p className="sub">
        {note ||
          (up
            ? "This account is only for " + ui.name + " and gets its own ID (" + ui.prefix + "-XXXXXX)."
            : "Use your " + ui.name + " username and password. Your accounts in the other sections are separate.")}
      </p>
      <div className="seg" style={{ gridTemplateColumns: `repeat(${Math.max(licensed.length, 1)},1fr)` }} role="tablist" aria-label="Section">
        {licensed.map((m) => (
          <button key={m} type="button" role="tab" aria-selected={m === module} onClick={() => chooseModule(m)}>
            {MODULE_UI[m].icon} {MODULE_UI[m].short}
          </button>
        ))}
      </div>
      <div className="seg" role="tablist" aria-label="Sign in or sign up">
        <button type="button" role="tab" aria-selected={!up} onClick={() => chooseMode("in")}>
          Sign in
        </button>
        <button type="button" role="tab" aria-selected={up} onClick={() => chooseMode("up")}>
          Sign up
        </button>
      </div>
      <form noValidate onSubmit={submitForm}>
        {up ? (
          <input name="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name" aria-label="Full name" autoComplete="name" />
        ) : null}
        <input
          name="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder={up ? "Choose a username (letters, numbers, . or _)" : "Username"}
          aria-label="Username"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
        />
        <input
          name="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password (6+ characters)"
          aria-label="Password"
          autoComplete={up ? "new-password" : "current-password"}
        />
        {up ? (
          <>
            <input
              name="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email (optional, for receipts and updates)"
              aria-label="Email (optional)"
              autoComplete="email"
            />
            <input
              name="phone"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="Mobile (optional, for WhatsApp updates)"
              aria-label="Mobile (optional)"
              autoComplete="tel"
              inputMode="tel"
            />
          </>
        ) : null}
        <p className="err" role="alert">
          {error}
        </p>
        <button className="btn" type="submit" disabled={busy} style={{ justifyContent: "center" }}>
          {up ? "Create account" : "Sign in"}
        </button>
      </form>
      {up ? null : (
        <p style={{ margin: "12px 0 0", fontSize: 14 }}>
          <button
            type="button"
            className="lk"
            onClick={() => {
              setError("");
              setStep("forgot");
            }}
          >
            Forgot password?
          </button>
        </p>
      )}
    </Modal>
  );
}
