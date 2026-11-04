import { Suspense } from "react";
import type { Metadata } from "next";
import ItemPage from "@/components/agent/ItemPage";

// The item comes from the database for each request, so this route is rendered per request.
export const instant = false;

export const metadata: Metadata = { title: "Job Processing" };

// [id] is the vacancy slug. The vacancy is read in the browser.
export default function VacancyPage({ params }: PageProps<"/jobs/[id]">) {
  return (
    <Suspense fallback={<p className="wrap">Loading…</p>}>
      {params.then(({ id }) => (
        <ItemPage module="job" slug={id} />
      ))}
    </Suspense>
  );
}
