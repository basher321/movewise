import type { Metadata } from "next";
import Button from "@/components/Button";
import Card from "@/components/Card";
import LiveProgress from "@/components/LiveProgress";
import PageShell from "@/components/PageShell";
import PartnerStrip from "@/components/PartnerStrip";
import DestinationChips from "@/components/agent/DestinationChips";
import StudyAgent from "@/components/agent/StudyAgent";

export const metadata: Metadata = { title: "Student Consultancy" };

const DASHBOARD = [
  ["🗺️", "Application roadmap", "A dated plan from today to your visa."],
  ["📋", "Document checklist", "What to prepare, in what format."],
  ["🎓", "University & course search", "Filter by country, tuition and intake."],
  ["📍", "Application tracking", "Live status on every application."],
  ["🌍", "Explore study destinations", "Costs, scholarships and life abroad."],
  ["✅", "Eligibility & requirements", "Know where you stand in minutes."],
  ["📊", "Student application dashboard", "All your progress in one view."],
] as const;

export default function ConsultancyPage() {
  return (
    <PageShell accent="#0EA5A4">
      <div className="hero">
        <div className="wrap">
          <div>
            <h1>Study abroad with a clear plan from day one.</h1>
            <p className="lead">
              Find the right university, prepare the right documents and follow your application until the visa decision.
            </p>
            <div className="acts">
              <Button href="#s-agent">Find my universities</Button>
            </div>
          </div>
          <LiveProgress title="Application tracking" publicTitle="Universities open now" modules={["study"]} />
        </div>
      </div>

      <section id="s-agent">
        <div className="wrap">
          <StudyAgent />
        </div>
      </section>

      <section className="band">
        <div className="wrap">
          <div className="head">
            <h2>Your application roadmap</h2>
            <p>Five steps, each with its own tools.</p>
          </div>
          <div className="road">
            <div>
              <h3>Explore destinations</h3>
              <p>Compare cost, scholarships and lifestyle.</p>
            </div>
            <div>
              <h3>Check eligibility</h3>
              <p>Requirements for your profile.</p>
            </div>
            <div>
              <h3>Choose a university</h3>
              <p>Search by course, tuition and intake.</p>
            </div>
            <div>
              <h3>Submit documents</h3>
              <p>Follow a country-specific checklist.</p>
            </div>
            <div>
              <h3>Track progress</h3>
              <p>See every update live.</p>
            </div>
          </div>
        </div>
      </section>

      <section>
        <div className="wrap">
          <div className="head">
            <h2>Everything you need in one dashboard</h2>
          </div>
          <div className="grid">
            {DASHBOARD.map(([ico, title, text]) => (
              <Card key={title}>
                <div className="ico">{ico}</div>
                <h3>{title}</h3>
                <p>{text}</p>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <DestinationChips module="study" title="Study destinations" />

      <PartnerStrip module="study" />

      <div className="cta">
        <h2>Ready to check your eligibility?</h2>
        <p>Share your results and goals. We will get back to you soon.</p>
        <Button href="/contact">Book a consultation</Button>
      </div>
    </PageShell>
  );
}
