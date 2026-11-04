import type { CSSProperties } from "react";
import Button from "@/components/Button";
import Card from "@/components/Card";
import HomeHero from "@/components/home/HomeHero";
import PopularNow from "@/components/home/PopularNow";
import IfLicensed from "@/components/IfLicensed";
import PageShell from "@/components/PageShell";

export default function HomePage() {
  return (
    <PageShell accent="brand">
      <HomeHero />

      <section>
        <div className="wrap">
          <div className="head">
            <h2>Ways we help you go further</h2>
            <p>Pick the path that fits your goal. You can combine them.</p>
          </div>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))" }}>
            <IfLicensed module="course">
              <Card href="/courses" className="path" accent="#4F46E5">
                <div className="ico">📚</div>
                <h3>Courses</h3>
                <p>Practical courses with a clear syllabus and a certificate.</p>
                <b>Explore courses →</b>
              </Card>
            </IfLicensed>
            <IfLicensed module="study">
              <Card href="/consultancy" className="path" accent="#0EA5A4">
                <div className="ico">🎓</div>
                <h3>Student Consultancy</h3>
                <p>University search, documents and visa support, with live tracking.</p>
                <b>Plan your studies →</b>
              </Card>
            </IfLicensed>
            <IfLicensed module="job">
              <Card href="/jobs" className="path" accent="#D97706">
                <div className="ico">🛂</div>
                <h3>Job Processing</h3>
                <p>Verified employers, clear costs and written contracts.</p>
                <b>Find jobs abroad →</b>
              </Card>
            </IfLicensed>
            <IfLicensed module="visa">
              <Card href="/immigration" className="path" accent="#E11D48">
                <div className="ico">🌍</div>
                <h3>Immigration Processing</h3>
                <p>Visit, family, work and residence visas for every country, with live tracking.</p>
                <b>Find your visa →</b>
              </Card>
            </IfLicensed>
          </div>
        </div>
      </section>

      <section className="band">
        <div className="wrap">
          <div className="head">
            <h2>How it works</h2>
            <p>From first conversation to your first day abroad.</p>
          </div>
          <div className="road" style={{ "--n": 4 } as CSSProperties}>
            <div>
              <h3>1. Free consultation</h3>
              <p>Tell us your goal. We map your options.</p>
            </div>
            <div>
              <h3>2. Build your plan</h3>
              <p>Courses, eligibility and a dated roadmap.</p>
            </div>
            <div>
              <h3>3. We handle the process</h3>
              <p>Applications, documents and permits.</p>
            </div>
            <div>
              <h3>4. Fly with confidence</h3>
              <p>Pre-departure briefing and ongoing support.</p>
            </div>
          </div>
        </div>
      </section>

      <PopularNow />

      <div className="cta">
        <h2>Your next step starts with one conversation.</h2>
        <p>Book a free consultation. An advisor will get back to you soon.</p>
        <Button href="/contact">Book consultation</Button>
      </div>
    </PageShell>
  );
}
