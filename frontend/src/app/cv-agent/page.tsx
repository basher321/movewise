import type { Metadata } from "next";
import { Suspense } from "react";
import CvAgentView from "@/components/cv/CvAgentView";

export const metadata: Metadata = { title: "AI CV Agent" };

// B28: the AI CV Agent - one place for every service (Core, any signed-in applicant).
export default function CvAgentPage() {
  return (
    <Suspense fallback={null}>
      <CvAgentView />
    </Suspense>
  );
}
