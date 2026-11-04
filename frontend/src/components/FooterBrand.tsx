"use client";

import Link from "next/link";
import IfLicensed from "./IfLicensed";
import { useSettings } from "./SettingsProvider";

// Footer text and links from Settings; "Verify certificate" only when the course module is licensed.
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
        {" · "}
        <Link href="/admin" style={{ fontWeight: 600 }}>
          Admin panel
        </Link>
        {" · "}
        <Link href="/super-admin" style={{ fontWeight: 600 }}>
          Super Admin
        </Link>
      </span>
    </div>
  );
}
