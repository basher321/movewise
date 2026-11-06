"use client";

import { useEffect, useState } from "react";
import { COUNTRY_FLAGS, listRemoteJobs, listUniversities, listVacancies, listVisaPrograms } from "@/lib/api";

// "Popular destinations": the countries of what is published now. Hidden while there are none.
export default function DestinationChips({ module, title }: { module: "study" | "job" | "visa" | "remote"; title: string }) {
  const [countries, setCountries] = useState<string[]>([]);

  useEffect(() => {
    let live = true;
    const load =
      module === "study" ? listUniversities() : module === "visa" ? listVisaPrograms() : module === "remote" ? listRemoteJobs() : listVacancies();
    void load
      .then((items) => {
        if (live) setCountries([...new Set(items.map((x) => x.country))].sort());
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [module]);

  if (!countries.length) return null;

  return (
    <section style={{ paddingTop: 0 }}>
      <div className="wrap">
        <div className="head">
          <h2>{title}</h2>
        </div>
        <div className="chips">
          {countries.map((c) => (
            <span key={c}>
              {COUNTRY_FLAGS[c] ?? "🌐"} {c}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
