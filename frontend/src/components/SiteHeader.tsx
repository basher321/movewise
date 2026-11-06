"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { MODULES, type Module } from "@/lib/api";
import AccountsMenu from "./AccountsMenu";
import Button from "./Button";
import { useSession } from "./SessionProvider";
import { isLicensed, useSettings } from "./SettingsProvider";

const MENU: { href: string; label: string; module?: Module }[] = [
  { href: "/", label: "Home" },
  { href: "/courses", label: "Courses", module: "course" },
  { href: "/consultancy", label: "Student Consultancy", module: "study" },
  { href: "/jobs", label: "Job Processing", module: "job" },
  { href: "/immigration", label: "Immigration", module: "visa" },
  { href: "/remote-jobs", label: "Remote Jobs", module: "remote" },
  { href: "/success-stories", label: "Success Stories" },
  { href: "/contact", label: "Contact" },
];

// The original logo from F01, used when Settings has no logo.
const DEFAULT_LOGO = "/logo.png";

export default function SiteHeader() {
  const pathname = usePathname();
  const { settings, licence } = useSettings();
  const { session, openAuth } = useSession();
  const [brokenLogo, setBrokenLogo] = useState<string | null>(null);
  const name = settings?.name ?? "";
  const logo = settings?.logo_url || DEFAULT_LOGO;
  const licensed = MODULES.filter((m) => isLicensed(licence, m));
  const signedIn = licensed.some((m) => session?.applicants[m]);

  return (
    <header>
      <div className="wrap">
        <nav>
          <Link className="logo" href="/" aria-label={`${name} home`}>
            {brokenLogo !== logo ? (
              <Image
                src={logo}
                alt={name}
                width={340}
                height={233}
                priority
                unoptimized={logo.startsWith("data:")}
                onError={() => setBrokenLogo(logo)}
              />
            ) : (
              <span>{name}</span>
            )}
          </Link>
          <ul id="menu">
            {MENU.filter((item) => !item.module || isLicensed(licence, item.module)).map((item) => {
              const on = pathname === item.href;
              return (
                <li key={item.href}>
                  <Link href={item.href} className={on ? "on" : undefined} aria-current={on ? "page" : undefined}>
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
          <div className="auth">
            {signedIn ? (
              <AccountsMenu modules={licensed} />
            ) : licensed.length > 0 ? (
              <>
                <Button variant="ghost" size="sm" onClick={() => openAuth({ mode: "in" })}>
                  Sign in
                </Button>
                <Button size="sm" onClick={() => openAuth({ mode: "up" })}>
                  Sign up
                </Button>
              </>
            ) : null}
          </div>
        </nav>
      </div>
    </header>
  );
}
