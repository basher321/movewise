"use client";

import { useEffect, useState } from "react";
import { listRemoteJobs, type Vacancy } from "@/lib/api";
import Card from "../Card";

// "Explore remote roles": open remote jobs with a verified employer. Hidden while there are none.
export default function OpenRemoteJobs() {
  const [jobs, setJobs] = useState<Vacancy[]>([]);

  useEffect(() => {
    let live = true;
    void listRemoteJobs()
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
    <section id="r-roles">
      <div className="wrap">
        <div className="head">
          <h2>Explore remote roles</h2>
          <p>Work from home for verified employers.</p>
        </div>
        <div className="grid">
          {jobs.slice(0, 12).map((v) => (
            <Card key={v.id} href={"/remote-jobs/" + v.slug}>
              <div className="ico">💻</div>
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
