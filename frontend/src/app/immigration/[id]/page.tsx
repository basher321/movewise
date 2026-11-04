import { Suspense } from "react";
import type { Metadata } from "next";
import ItemPage from "@/components/agent/ItemPage";

// The item comes from the database for each request, so this route is rendered per request.
export const instant = false;

export const metadata: Metadata = { title: "Immigration Processing" };

// [id] is the visa programme slug. The programme is read in the browser.
export default function VisaProgramPage({ params }: PageProps<"/immigration/[id]">) {
  return (
    <Suspense fallback={<p className="wrap">Loading…</p>}>
      {params.then(({ id }) => (
        <ItemPage module="visa" slug={id} />
      ))}
    </Suspense>
  );
}
