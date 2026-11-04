"use client";

import { useEffect, useState } from "react";
import { listPublicPartners, type Module, type PartnerType, type PublicPartner } from "@/lib/api";
import { isLicensed, useSettings } from "./SettingsProvider";

export const PARTNER_TYPE_LABELS: Record<PartnerType, string> = {
  university: "University",
  college: "College",
  employer: "Employer",
  recruitment_agency: "Recruitment partner",
  training_body: "Training partner",
  exam_board: "Exam board",
  visa_centre: "Visa application centre",
  law_firm: "Immigration law firm",
  other: "Partner",
};

const LINES: Record<Module, string> = {
  course: "Training and exam partners we work with.",
  study: "Universities and colleges we work with.",
  job: "Employers and recruitment partners we work with.",
  visa: "Visa centres and immigration partners we work with.",
};

// B18: "Our partners" on one module's page, with only that module's partners. Not shown when the
// module is not licensed, when there are no public partners, or when the list cannot be loaded.
export default function PartnerStrip({ module }: { module: Module }) {
  const { licence } = useSettings();
  const on = isLicensed(licence, module);
  const [partners, setPartners] = useState<PublicPartner[]>([]);

  useEffect(() => {
    if (!on) return;
    let live = true;
    listPublicPartners(module)
      .then((list) => live && setPartners(list))
      .catch(() => live && setPartners([]));
    return () => {
      live = false;
    };
  }, [module, on]);

  if (!on || !partners.length) return null;

  return (
    <section>
      <div className="wrap">
        <div className="head">
          <h2>Our partners</h2>
          <p>{LINES[module]}</p>
        </div>
        <div className="grid">
          {partners.map((p) => {
            const body = (
              <>
                {p.logo_url ? (
                  <div className="plogo">
                    {/* eslint-disable-next-line @next/next/no-img-element -- the partner logo, served by the backend */}
                    <img src={p.logo_url} alt={p.name + " logo"} loading="lazy" />
                  </div>
                ) : (
                  <div className="ico" aria-hidden="true">
                    {p.name.trim().charAt(0).toUpperCase()}
                  </div>
                )}
                <h3>{p.name}</h3>
                <p>{[PARTNER_TYPE_LABELS[p.partner_type], p.country].filter(Boolean).join(" · ")}</p>
                {p.description ? <p style={{ marginTop: 8 }}>{p.description}</p> : null}
              </>
            );
            return p.website ? (
              <a key={p.id} className="card path" href={p.website} target="_blank" rel="noopener noreferrer">
                {body}
              </a>
            ) : (
              <div key={p.id} className="card">
                {body}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
