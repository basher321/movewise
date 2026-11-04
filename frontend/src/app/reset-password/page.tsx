import { Suspense } from "react";
import type { Metadata } from "next";
import PageShell from "@/components/PageShell";
import ResetPasswordForm from "@/components/auth/ResetPasswordForm";

export const metadata: Metadata = { title: "Reset password" };

// B15: where the "Forgot password?" email link leads (/reset-password?token=).
export default function ResetPasswordPage() {
  return (
    <PageShell accent="brand">
      <section>
        <div className="wrap" style={{ maxWidth: 460 }}>
          <h2 style={{ fontSize: 28, marginBottom: 6 }}>Choose a new password</h2>
          <p style={{ marginBottom: 18 }}>The link from the email works once, for 30 minutes.</p>
          <Suspense fallback={<p style={{ color: "var(--muted)" }}>Loading…</p>}>
            <ResetPasswordForm />
          </Suspense>
        </div>
      </section>
    </PageShell>
  );
}
