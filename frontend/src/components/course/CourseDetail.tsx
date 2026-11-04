"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type CSSProperties } from "react";
import { getCourse, isApiError, myEnrolments, NETWORK_MESSAGE, type Course, type Enrolment, type PayStart } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { useToast } from "../admin/Toast";
import Button from "../Button";
import { useSession } from "../SessionProvider";
import LoadError from "../LoadError";
import EnrolDialog from "./EnrolDialog";

const COUNT = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];

// /courses/[slug] (showCourse() in the reference).
export default function CourseDetail({ slug }: { slug: string }) {
  const router = useRouter();
  const { session, reload, openAuth } = useSession();
  const { toast, toastNode } = useToast();
  // undefined while loading; null when the course does not exist or is not published.
  const [course, setCourse] = useState<Course | null | undefined>(undefined);
  const [mine, setMine] = useState<Enrolment | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [enrolling, setEnrolling] = useState(false);
  const account = session?.applicants.course;

  useEffect(() => {
    let live = true;
    getCourse(slug)
      .then((c) => {
        if (live) {
          setCourse(c);
          setError("");
        }
      })
      .catch((err: unknown) => {
        if (!live) return;
        if (isApiError(err) && err.code === "NOT_FOUND") setCourse(null);
        else if (!(isApiError(err) && err.code === "MODULE_NOT_LICENSED")) setError(isApiError(err) ? err.message : NETWORK_MESSAGE);
      });
    return () => {
      live = false;
    };
  }, [slug, attempt]);

  useEffect(() => {
    let live = true;
    if (!account) return;
    void myEnrolments()
      .then((list) => {
        if (live) setMine(list.find((e) => e.course.slug === slug && e.status !== "cancelled") ?? null);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [account, slug]);

  if (error) return <LoadError message={error} onRetry={() => setAttempt(attempt + 1)} />;
  if (course === undefined) return null;
  const isOwned = !!account && (mine?.status === "active" || mine?.status === "completed");
  const waiting = !!account && mine?.status === "awaiting_payment" && mine.payment_status === "pending_verify";
  if (course === null) {
    return (
      <section>
        <div className="wrap">
          <div className="card">
            <h3>Course not found</h3>
            <div className="cr">
              <Button variant="ghost" size="sm" href="/courses">
                See all courses
              </Button>
            </div>
          </div>
        </div>
      </section>
    );
  }

  function start() {
    if (account) {
      setEnrolling(true);
      return;
    }
    openAuth({ mode: "up", module: "course", note: "Create your Courses account to enrol, then sign in.", after: () => setEnrolling(true) });
  }

  // Only bank / office payments come back here; card and bKash payments go to the gateway.
  function done(payment: PayStart) {
    setEnrolling(false);
    void reload();
    if (payment.status === "pending_verify") toast("Payment reference sent. We will email you once it is verified.");
    else router.push("/profile/course");
  }

  const full = { width: "100%", justifyContent: "center" };

  return (
    <div style={{ "--a": course.colour } as CSSProperties}>
      <div className="hero">
        <div className="wrap">
          <div>
            <Link className="crumb" href="/courses">
              ← All courses
            </Link>
            <br />
            <span className="tag">{course.group_name}</span>
            <h1>{course.title}</h1>
            <p className="lead">{course.description}</p>
            <div className="meta">
              {course.duration ? <span>⏱ {course.duration}</span> : null}
              {course.level ? <span>📶 {course.level}</span> : null}
              <span>🏅 Certificate included</span>
            </div>
          </div>
          <div className="vis">
            <div className="price">
              {formatMoney(course.price_poisha)} <small>one-time</small>
            </div>
            <p style={{ color: "var(--muted)", margin: "0 0 18px", fontSize: 15 }}>One payment. Your course certificate is included.</p>
            {isOwned ? (
              <Link className="btn" href="/profile/course" style={full}>
                Enrolled ✓ Open my profile
              </Link>
            ) : waiting ? (
              <Link className="btn ghost" href="/profile/course" style={full}>
                Payment waiting for verification
              </Link>
            ) : (
              <button className="btn" type="button" style={full} onClick={start}>
                Enrol &amp; purchase
              </button>
            )}
            <ul className="list" style={{ marginTop: 20 }}>
              <li>Pay online or at our office</li>
              <li>Follow your enrolment in your profile</li>
              <li>Certificate generated for you, view-only until approved</li>
            </ul>
          </div>
        </div>
      </div>
      <section>
        <div className="wrap">
          <div className="head">
            <h2>What you will learn</h2>
          </div>
          <div className="grid">
            {course.learn_points.map((x) => (
              <div className="card" key={x}>
                <div className="ico">✓</div>
                <h3 style={{ fontSize: 18, margin: 0 }}>{x}</h3>
              </div>
            ))}
          </div>
        </div>
      </section>
      <section className="band">
        <div className="wrap">
          <div className="head">
            <h2>Syllabus</h2>
            <p>
              {course.duration ? course.duration + ", " : ""}
              {COUNT[course.syllabus.length] ?? course.syllabus.length} {course.syllabus.length === 1 ? "module" : "modules"}.
            </p>
          </div>
          <div className="grid">
            {course.syllabus.map((x, i) => (
              <div className="card mod" key={x}>
                <b>{i + 1}</b>
                <h3>{x}</h3>
              </div>
            ))}
          </div>
        </div>
      </section>
      {enrolling && account ? <EnrolDialog course={course} account={account} onClose={() => setEnrolling(false)} onDone={done} /> : null}
      {toastNode}
    </div>
  );
}
