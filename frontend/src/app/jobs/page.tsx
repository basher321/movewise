import type { Metadata } from "next";
import Button from "@/components/Button";
import PageShell from "@/components/PageShell";
import PartnerStrip from "@/components/PartnerStrip";
import DestinationChips from "@/components/agent/DestinationChips";
import OpenJobs from "@/components/agent/OpenJobs";
import { ModuleAgent } from "@/components/agent/StudyAgent";
import { DOCUMENT_TYPES } from "@/lib/api";

export const metadata: Metadata = { title: "Job Processing" };

export default function JobsPage() {
  return (
    <PageShell accent="#D97706">
      <div className="hero">
        <div className="wrap">
          <div>
            <h1>Work abroad through a process you can trust.</h1>
            <p className="lead">Verified employers, clear costs and written contracts, with every step visible online.</p>
            <div className="acts">
              <Button href="#j-agent">Find my job match</Button>
              <Button variant="ghost" href="#j-roles">
                Explore opportunities
              </Button>
            </div>
          </div>
          <div className="vis">
            <h3>Job application</h3>
            <div className="row ok">
              <span>✓</span>
              <div>
                Profile reviewed<small>By your advisor</small>
              </div>
            </div>
            <div className="row ok">
              <span>✓</span>
              <div>
                Employer interview<small>Date and result in your profile</small>
              </div>
            </div>
            <div className="row">
              <span>•</span>
              <div>
                Work permit<small>Every update online</small>
              </div>
            </div>
            <div className="bar">
              <i style={{ width: "55%" }}></i>
            </div>
          </div>
        </div>
      </div>

      <section id="j-agent">
        <div className="wrap">
          <ModuleAgent module="job" />
        </div>
      </section>

      <OpenJobs />

      <section className="band">
        <div className="wrap two">
          <div>
            <h2>Eligibility &amp; documents</h2>
            <p style={{ color: "#9AA7C7", marginTop: 14 }}>Know what you need before you apply.</p>
            <ul className="list">
              {DOCUMENT_TYPES.job.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          </div>
          <div>
            <h2>Clear costs, written contracts</h2>
            <p style={{ color: "#9AA7C7", margin: "14px 0 22px" }}>
              Every job shows its salary, contract, benefits and our processing fee before you apply. You pay online or at our office and
              get an invoice for every payment.
            </p>
          </div>
        </div>
      </section>

      <DestinationChips module="job" title="Where our jobs are" />

      <PartnerStrip module="job" />

      <div className="cta">
        <h2>Start your job application</h2>
        <p>Tell us your skills. We match you with verified employers.</p>
        <Button href="#j-agent">Apply now</Button>
      </div>
    </PageShell>
  );
}
