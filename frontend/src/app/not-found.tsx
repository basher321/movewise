import type { Metadata } from "next";
import EmptyState from "@/components/EmptyState";
import PageShell from "@/components/PageShell";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <PageShell accent="#4F46E5">
      <section>
        <div className="wrap">
          <EmptyState title="Page not found" action={{ label: "Go home", href: "/" }} />
        </div>
      </section>
    </PageShell>
  );
}
