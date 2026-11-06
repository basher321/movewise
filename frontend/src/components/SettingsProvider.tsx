"use client";

import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getLicence, getPublicSettings, isApiError, NETWORK_MESSAGE, type LicenceView, type Module, type PublicSettings } from "@/lib/api";
import LoadError from "./LoadError";

type SettingsContextValue = {
  settings: PublicSettings | null; // null until loaded
  licence: LicenceView | null; // null until loaded
  reload: () => Promise<void>;
};

const SettingsContext = createContext<SettingsContextValue>({
  settings: null,
  licence: null,
  reload: async () => {},
});

export function useSettings(): SettingsContextValue {
  return useContext(SettingsContext);
}

export function isLicensed(licence: LicenceView | null, module: Module): boolean {
  return !!licence && licence.modules[module];
}

// Page names from the reference (T); the home page title is the company name alone.
const TITLES: Record<string, string> = {
  "/courses": "Courses",
  "/consultancy": "Student Consultancy",
  "/jobs": "Job Processing",
  "/immigration": "Immigration Processing",
  "/remote-jobs": "Remote Jobs",
  "/success-stories": "Success Stories",
  "/contact": "Contact",
  "/profile": "My profile",
  "/admin": "Admin panel",
  "/super-admin": "Super Admin",
  "/reset-password": "Reset password",
  "/verify": "Verify certificate",
};

function TitleSync({ name }: { name: string }) {
  const pathname = usePathname();
  useEffect(() => {
    const page = TITLES["/" + (pathname.split("/")[1] ?? "")];
    const wanted = page ? page + " – " + name : name;
    const apply = () => {
      if (document.title !== wanted) document.title = wanted;
    };
    apply();
    // Next.js writes the page metadata title after navigation; keep the branded one.
    const observer = new MutationObserver(apply);
    observer.observe(document.head, { subtree: true, childList: true, characterData: true });
    return () => observer.disconnect();
  }, [pathname, name]);
  return null;
}

// The browser tab icon follows the Settings logo; the layout's /logo.png stays when none is set.
function IconSync({ logo }: { logo: string | null }) {
  useEffect(() => {
    if (!logo) return;
    for (const link of document.querySelectorAll<HTMLLinkElement>('link[rel="icon"]')) {
      if (link.href !== logo) link.href = logo;
    }
  }, [logo]);
  return null;
}

// Loads PublicSettings and Licence once at app start. reload() refreshes both,
// so saving Settings or applying a key updates the whole site without a page refresh.
export default function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<PublicSettings | null>(null);
  const [licence, setLicence] = useState<LicenceView | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  const reload = useCallback(async () => {
    const [s, l] = await Promise.all([getPublicSettings(), getLicence()]);
    setSettings(s);
    setLicence(l);
    setError("");
  }, []);

  useEffect(() => {
    let live = true;
    Promise.all([getPublicSettings(), getLicence()])
      .then(([s, l]) => {
        if (!live) return;
        setSettings(s);
        setLicence(l);
        setError("");
      })
      .catch((err: unknown) => {
        // The page shell still renders; the banner says what is wrong and offers Retry.
        if (live) setError(isApiError(err) && err.code !== "INTERNAL" ? err.message : NETWORK_MESSAGE);
      });
    return () => {
      live = false;
    };
  }, [attempt]);

  return (
    <SettingsContext.Provider value={{ settings, licence, reload }}>
      {settings ? <TitleSync name={settings.name} /> : null}
      {settings ? <IconSync logo={settings.logo_url} /> : null}
      {error ? <LoadError message={error} onRetry={() => setAttempt(attempt + 1)} /> : null}
      {children}
    </SettingsContext.Provider>
  );
}
