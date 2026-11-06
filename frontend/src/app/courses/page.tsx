import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Button from "@/components/Button";
import LiveProgress from "@/components/LiveProgress";
import PageShell from "@/components/PageShell";
import PartnerStrip from "@/components/PartnerStrip";
import CourseGroups from "@/components/course/CourseGroups";

export const metadata: Metadata = { title: "Courses" };

export default function CoursesPage() {
  return (
    <PageShell accent="brand">
      <div className="hero">
        <div className="wrap">
          <div>
            <h1>Learn practical skills and earn a certificate.</h1>
            <p className="lead">Courses with a clear syllabus, simple payment and a certificate anyone can verify online.</p>
            <div className="acts">
              <Button href="#c-list">Enrol in a course</Button>
              <Button variant="ghost" href="#c-list">
                See all courses
              </Button>
            </div>
          </div>
          <LiveProgress title="My courses & learning" publicTitle="Our courses" modules={["course"]} />
        </div>
      </div>

      <CourseGroups />

      <section className="band">
        <div className="wrap">
          <div className="head">
            <h2>How learning works</h2>
          </div>
          <div className="road" style={{ "--n": 4 } as CSSProperties}>
            <div>
              <h3>Pick a track</h3>
              <p>Choose by goal and level.</p>
            </div>
            <div>
              <h3>Enrol online</h3>
              <p>Pay by card, mobile banking or at our office.</p>
            </div>
            <div>
              <h3>Learn and practise</h3>
              <p>Work through every module of the syllabus.</p>
            </div>
            <div>
              <h3>Get certified</h3>
              <p>A certificate anyone can verify online.</p>
            </div>
          </div>
        </div>
      </section>

      <PartnerStrip module="course" />

      <div className="cta">
        <h2>Not sure which course fits?</h2>
        <p>Talk to an advisor and get a learning path in one call.</p>
        <Button href="/contact">Book a free call</Button>
      </div>
    </PageShell>
  );
}
