"use client";

import { Fragment } from "react";
import Card from "@/components/Card";
import { useSettings } from "@/components/SettingsProvider";

// Office and contact details from Settings (applyBrand() in the reference).
export default function ContactCard() {
  const { settings } = useSettings();
  const lines = settings ? [settings.address, settings.hours, settings.email, settings.phone].filter(Boolean) : [];
  return (
    <Card>
      <h3>Office &amp; contact details</h3>
      <p style={{ marginTop: 8 }}>
        {lines.map((line, i) => (
          <Fragment key={i}>
            {i > 0 ? <br /> : null}
            {line}
          </Fragment>
        ))}
        {settings?.facebook ? (
          <>
            {lines.length ? <br /> : null}
            <a href={settings.facebook} target="_blank" rel="noopener" style={{ color: "var(--a)", fontWeight: 600 }}>
              {settings.name} on Facebook
            </a>
          </>
        ) : null}
      </p>
    </Card>
  );
}
