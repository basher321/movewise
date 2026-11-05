"use client";

import Link from "next/link";
import IfLicensed from "./IfLicensed";
import { useSettings } from "./SettingsProvider";

// Footer text and links from Settings; "Verify certificate" only when the course module is licensed.
// Staff pages (/admin, /super-admin) are not linked from public pages; staff open those URLs directly.
export default function FooterBrand({ year }: { year: string }) {
  const { settings } = useSettings();
  return (
    <div className="wrap">
      <span>
        © {year} {settings?.name ?? ""}. All rights reserved.
      </span>
      <span>
        <IfLicensed module="course">
          <Link href="/verify" style={{ fontWeight: 600 }}>
            Verify certificate
          </Link>
          {" · "}
        </IfLicensed>
        {settings?.facebook ? (
          <>
            <a href={settings.facebook} target="_blank" rel="noopener" style={{ fontWeight: 600 }}>
              Facebook
            </a>
            {" · "}
          </>
        ) : null}
        <Link href="/profile">Student login</Link>
      </span>
    </div>
  );
}
