"use client";

import { useCallback, useEffect, useState } from "react";
import { useSettings } from "@/components/SettingsProvider";
import { getSession, type AdminUser } from "@/lib/api";
import AdminAuth from "./AdminAuth";
import { Panel } from "./AdminApp";

// /super-admin (B14): the Super Admin sign-in card, or the full admin panel for the Super Admin.
export default function SuperAdminApp() {
  const { licence } = useSettings();
  // undefined while loading; null when nobody (or a deactivated admin) is signed in.
  const [admin, setAdmin] = useState<AdminUser | null | undefined>(undefined);

  const refresh = useCallback(async () => {
    const session = await getSession();
    setAdmin(session.admin);
  }, []);
  const changed = useCallback(() => void refresh(), [refresh]);

  useEffect(() => {
    let live = true;
    void getSession().then((session) => {
      if (live) setAdmin(session.admin);
    });
    return () => {
      live = false;
    };
  }, []);

  if (admin === undefined || !licence) return null;
  if (admin?.role !== "super_admin") return <AdminAuth variant="super" staffSignedIn={admin !== null} onSignedIn={changed} />;
  return <Panel admin={admin} licence={licence} onSignedOut={changed} onAccountSaved={changed} title="Super Admin panel" />;
}
