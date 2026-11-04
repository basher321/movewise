import { Suspense } from "react";
import type { Metadata } from "next";
import ItemPage from "@/components/agent/ItemPage";

// The item comes from the database for each request, so this route is rendered per request.
export const instant = false;

export const metadata: Metadata = { title: "Student Consultancy" };

// [id] is the university slug. The university is read in the browser.
export default function UniversityPage({ params }: PageProps<"/consultancy/[id]">) {
  return (
    <Suspense fallback={<p className="wrap">Loading…</p>}>
      {params.then(({ id }) => (
        <ItemPage module="study" slug={id} />
      ))}
    </Suspense>
  );
}
