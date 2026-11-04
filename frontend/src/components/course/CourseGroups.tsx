"use client";

import Link from "next/link";
import { useEffect, useState, type CSSProperties } from "react";
import { isApiError, listCourseGroups, NETWORK_MESSAGE, type Course, type PublicCourseGroup } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import LoadError from "../LoadError";

// The first sentence of the description, for the card.
function summary(text: string): string {
  const first = text.split(/(?<=[.!?])\s/)[0] ?? "";
  return first.length > 140 ? first.slice(0, 137) + "…" : first;
}

// A course card (the data-cards renderer in the reference).
function CourseCards({ courses }: { courses: Course[] }) {
  return courses.map((c) => (
    <Link key={c.id} className="card path" href={"/courses/" + c.slug} style={{ "--a": c.colour } as CSSProperties}>
      <div className="ico">{c.icon}</div>
      <h3>{c.title}</h3>
      <p>{summary(c.description)}</p>
      <b>{formatMoney(c.price_poisha)} · View details →</b>
    </Link>
  ));
}

// The course groups of /courses (headings and order set by the super admin in Catalog).
export default function CourseGroups() {
  const [groups, setGroups] = useState<PublicCourseGroup[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    listCourseGroups()
      .then((list) => {
        if (live) {
          setGroups(list);
          setError("");
        }
      })
      .catch((err: unknown) => {
        // An unlicensed module shows the locked card from the layout instead.
        if (live && !(isApiError(err) && err.code === "MODULE_NOT_LICENSED")) {
          setError(isApiError(err) ? err.message : NETWORK_MESSAGE);
        }
      });
    return () => {
      live = false;
    };
  }, [attempt]);

  if (error) return <LoadError message={error} onRetry={() => setAttempt(attempt + 1)} />;
  if (groups === null) {
    return (
      <section id="c-list">
        <div className="wrap">
          <p style={{ color: "var(--muted)" }}>Loading…</p>
        </div>
      </section>
    );
  }
  if (!groups.length) {
    return (
      <section id="c-list">
        <div className="wrap">
          <div className="card" style={{ textAlign: "center" }}>
            <h3>New courses are coming soon</h3>
            <p style={{ margin: 0 }}>Contact us and we will tell you when the next batch opens.</p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <>
      {groups.map((g, i) => (
        <section key={g.id} id={i === 0 ? "c-list" : undefined} style={i === 0 ? undefined : { paddingTop: 0 }}>
          <div className="wrap">
            <div className="head">
              <h2>{g.name}</h2>
              {g.description ? <p>{g.description}</p> : null}
            </div>
            <div className="grid">
              <CourseCards courses={g.courses} />
            </div>
          </div>
        </section>
      ))}
    </>
  );
}
