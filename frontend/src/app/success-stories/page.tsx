import type { Metadata } from "next";
import Button from "@/components/Button";
import PageShell from "@/components/PageShell";
import SuccessStories from "@/components/success/SuccessStories";

export const metadata: Metadata = { title: "Success Stories" };

// Success Stories: every completed journey shows here automatically, with a summary per section.
export default function SuccessStoriesPage() {
  return (
    <PageShell accent="brand">
      <div className="hero">
        <div className="wrap" style={{ gridTemplateColumns: "1fr" }}>
          <div>
            <h1>Real journeys, real results.</h1>
            <p className="lead">
              Every story here is a real case that reached its last stage with our team. It appears automatically the moment a journey is completed.
            </p>
            <div className="acts">
              <Button href="/contact">Start your journey</Button>
            </div>
          </div>
        </div>
      </div>
      <SuccessStories />
    </PageShell>
  );
}
