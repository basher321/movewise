import { Suspense } from "react";
import type { Metadata } from "next";
import ApplicationPage from "@/components/agent/ApplicationPage";

// The item comes from the database for each request, so this route is rendered per request.
export const instant = false;

export const metadata: Metadata = { title: "Student Consultancy" };

// [id] is the university slug. The application itself is read in the browser.
export default function UniversityApplicationPage({ params }: PageProps<"/consultancy/[id]/apply">) {
  return (
    <Suspense fallback={<p className="wrap">Loading…</p>}>
      {params.then(({ id }) => (
        <ApplicationPage module="study" slug={id} />
      ))}
    </Suspense>
  );
}
