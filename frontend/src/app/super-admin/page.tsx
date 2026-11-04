import type { Metadata } from "next";
import { Suspense } from "react";
import SuperAdminApp from "@/components/admin/SuperAdminApp";
import PageShell from "@/components/PageShell";

export const metadata: Metadata = { title: "Super Admin" };

// B14: the Super Admin's own sign-in, first-time sign-up and panel.
export default function SuperAdminPage() {
  return (
    <PageShell accent="#7C3AED">
      {/* The panel reads ?tab= from the URL, which needs a Suspense boundary. */}
      <Suspense fallback={null}>
        <SuperAdminApp />
      </Suspense>
    </PageShell>
  );
}
