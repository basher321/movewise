"use client";

import { useEffect, useState } from "react";
import { COUNTRY_FLAGS, listVacancies, type Vacancy } from "@/lib/api";
import Card from "../Card";

// "Explore job opportunities": open jobs with a verified employer. Hidden while there are none.
export default function OpenJobs() {
  const [jobs, setJobs] = useState<Vacancy[]>([]);

  useEffect(() => {
    let live = true;
    void listVacancies()
      .then((list) => {
        if (live) setJobs(list);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);

  if (!jobs.length) return null;

  return (
    <section id="j-roles">
      <div className="wrap">
        <div className="head">
          <h2>Explore job opportunities</h2>
          <p>Open roles with verified employers.</p>
        </div>
        <div className="grid">
          {jobs.slice(0, 12).map((v) => (
            <Card key={v.id} href={"/jobs/" + v.slug}>
              <div className="ico">{COUNTRY_FLAGS[v.country] ?? "🛂"}</div>
              <h3>{v.title}</h3>
              <p>
                {v.employer} · {v.country} · ${v.salary_usd.toLocaleString("en-US")}/month
              </p>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}
