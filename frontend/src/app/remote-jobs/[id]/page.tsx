import { Suspense } from "react";
import type { Metadata } from "next";
import ItemPage from "@/components/agent/ItemPage";

// The item comes from the database for each request, so this route is rendered per request.
export const instant = false;

export const metadata: Metadata = { title: "Remote Jobs" };

// [id] is the remote job slug. The role is read in the browser.
export default function RemoteJobPage({ params }: PageProps<"/remote-jobs/[id]">) {
  return (
    <Suspense fallback={<p className="wrap">Loading…</p>}>
      {params.then(({ id }) => (
        <ItemPage module="remote" slug={id} />
      ))}
    </Suspense>
  );
}
