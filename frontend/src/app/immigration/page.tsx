import type { Metadata } from "next";
import Button from "@/components/Button";
import LiveProgress from "@/components/LiveProgress";
import PageShell from "@/components/PageShell";
import PartnerStrip from "@/components/PartnerStrip";
import DestinationChips from "@/components/agent/DestinationChips";
import OpenVisaPrograms from "@/components/agent/OpenVisaPrograms";
import { ModuleAgent } from "@/components/agent/StudyAgent";
import { DOCUMENT_TYPES } from "@/lib/api";

export const metadata: Metadata = { title: "Immigration Processing" };

// B19: Immigration Processing, built like the Job Processing page.
export default function ImmigrationPage() {
  return (
    <PageShell accent="#E11D48">
      <div className="hero">
        <div className="wrap">
          <div>
            <h1>Your visa, for any country, handled with care.</h1>
            <p className="lead">Visit, family, work, business and residence visas. Clear fees, a named advisor and every step visible online.</p>
            <div className="acts">
              <Button href="#v-agent">Find my visa programme</Button>
              <Button variant="ghost" href="#v-programs">
                Explore programmes
              </Button>
            </div>
          </div>
          <LiveProgress title="Visa application" publicTitle="Visa programmes" modules={["visa"]} />
        </div>
      </div>

      <section id="v-agent">
        <div className="wrap">
          <ModuleAgent module="visa" />
        </div>
      </section>

      <OpenVisaPrograms />

      <section className="band">
        <div className="wrap two">
          <div>
            <h2>Eligibility &amp; documents</h2>
            <p style={{ color: "#9AA7C7", marginTop: 14 }}>Most visas need these. Each programme lists its own extra papers.</p>
            <ul className="list">
              {DOCUMENT_TYPES.visa.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          </div>
          <div>
            <h2>Clear costs, honest advice</h2>
            <p style={{ color: "#9AA7C7", margin: "14px 0 22px" }}>
              Every programme shows the government fee, the processing time and our processing fee before you apply. You pay online or at our
              office and get an invoice for every payment.
            </p>
          </div>
        </div>
      </section>

      <DestinationChips module="visa" title="Countries we process" />

      <PartnerStrip module="visa" />

      <div className="cta">
        <h2>Start your visa application</h2>
        <p>Tell us where you want to go. We prepare your file and follow it to the decision.</p>
        <Button href="#v-agent">Apply now</Button>
      </div>
    </PageShell>
  );
}
