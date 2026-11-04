"use client";

import { useEffect, useState } from "react";
import { COUNTRY_FLAGS, listVisaPrograms, type VisaProgram } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import Card from "../Card";

// B19 "Explore visa programmes": the published programmes (like OpenJobs). Hidden while there are none.
export default function OpenVisaPrograms() {
  const [programs, setPrograms] = useState<VisaProgram[]>([]);

  useEffect(() => {
    let live = true;
    void listVisaPrograms()
      .then((list) => {
        if (live) setPrograms(list);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);

  if (!programs.length) return null;

  return (
    <section id="v-programs">
      <div className="wrap">
        <div className="head">
          <h2>Explore visa programmes</h2>
          <p>Every country and visa type we process, with clear fees.</p>
        </div>
        <div className="grid">
          {programs.slice(0, 12).map((p) => (
            <Card key={p.id} href={"/immigration/" + p.slug}>
              <div className="ico">{COUNTRY_FLAGS[p.country] ?? "🌍"}</div>
              <h3>{p.title}</h3>
              <p>
                {p.country} · {p.visa_type_label} · {formatMoney(p.fee_poisha)}
              </p>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}
