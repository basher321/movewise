import type { Metadata } from "next";
import Button from "@/components/Button";
import LiveProgress from "@/components/LiveProgress";
import PageShell from "@/components/PageShell";
import PartnerStrip from "@/components/PartnerStrip";
import DestinationChips from "@/components/agent/DestinationChips";
import OpenRemoteJobs from "@/components/agent/OpenRemoteJobs";
import { ModuleAgent } from "@/components/agent/StudyAgent";
import { DOCUMENT_TYPES, REMOTE_STAGES } from "@/lib/api";

export const metadata: Metadata = { title: "Remote Jobs" };

// Remote Jobs: built like the Job Processing page, for roles done from home (no visa or travel).
export default function RemoteJobsPage() {
  return (
    <PageShell accent="#059669">
      <div className="hero">
        <div className="wrap">
          <div>
            <h1>Work for global employers, from home.</h1>
            <p className="lead">Verified remote roles, clear costs and written contracts. No visa, no travel, and every step visible online.</p>
            <div className="acts">
              <Button href="#r-agent">Find my remote job</Button>
              <Button variant="ghost" href="#r-roles">
                Explore remote roles
              </Button>
            </div>
          </div>
          <LiveProgress title="Remote job application" publicTitle="Remote jobs open now" modules={["remote"]} />
        </div>
      </div>

      <section id="r-agent">
        <div className="wrap">
          <ModuleAgent module="remote" />
        </div>
      </section>

      <OpenRemoteJobs />

      <section className="band">
        <div className="wrap two">
          <div>
            <h2>Documents you need</h2>
            <p style={{ color: "#9AA7C7", marginTop: 14 }}>No passport, medical or police papers are needed. Just show your skills.</p>
            <ul className="list">
              {DOCUMENT_TYPES.remote.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          </div>
          <div>
            <h2>How it works</h2>
            <p style={{ color: "#9AA7C7", margin: "14px 0 22px" }}>
              Search and match, pay the processing fee, then follow every step online up to your offer letter and first day. You get an
              invoice for every payment.
            </p>
            <ul className="list">
              {REMOTE_STAGES.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <DestinationChips module="remote" title="Where our remote employers are" />

      <PartnerStrip module="remote" />

      <div className="cta">
        <h2>Start your remote job application</h2>
        <p>Tell us your skills. We match you with verified remote employers.</p>
        <Button href="#r-agent">Apply now</Button>
      </div>
    </PageShell>
  );
}
