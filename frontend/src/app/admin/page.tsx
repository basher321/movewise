import type { Metadata } from "next";
import { Suspense } from "react";
import AdminApp from "@/components/admin/AdminApp";
import PageShell from "@/components/PageShell";

export const metadata: Metadata = { title: "Admin panel" };

export default function AdminPage() {
  return (
    <PageShell accent="#7C3AED">
      {/* AdminApp reads ?tab= from the URL, which needs a Suspense boundary. */}
      <Suspense fallback={null}>
        <AdminApp />
      </Suspense>
    </PageShell>
  );
}
