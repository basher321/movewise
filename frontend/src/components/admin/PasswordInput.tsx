"use client";

import { useState, type InputHTMLAttributes } from "react";

// Eye icon for the show / hide password button; "off" draws the eye crossed out.
function EyeIcon({ off }: { off: boolean }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
      {off ? <path d="M3 3l18 18" /> : null}
    </svg>
  );
}

// A password box with a show / hide eye button inside it, used on the admin sign-in card,
// in "My account", and on the applicant sign-in / sign-up dialog and "Change password".
export default function PasswordInput(props: Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  const [shown, setShown] = useState(false);
  return (
    <div style={{ position: "relative" }}>
      <input {...props} type={shown ? "text" : "password"} style={{ ...props.style, paddingRight: 52 }} />
      <button
        type="button"
        onClick={() => setShown((v) => !v)}
        aria-label={shown ? "Hide password" : "Show password"}
        aria-pressed={shown}
        title={shown ? "Hide password" : "Show password"}
        style={{
          position: "absolute",
          top: "50%",
          right: 8,
          transform: "translateY(-50%)",
          width: 38,
          height: 38,
          display: "grid",
          placeItems: "center",
          border: 0,
          borderRadius: 10,
          background: "transparent",
          color: "var(--muted)",
          cursor: "pointer",
          padding: 0,
        }}
      >
        <EyeIcon off={shown} />
      </button>
    </div>
  );
}
