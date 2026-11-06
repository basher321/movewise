"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, type CSSProperties, type KeyboardEvent, type MouseEvent } from "react";
import { signOut, type Module } from "@/lib/api";
import { accentColour, MODULE_UI } from "./auth/modules";
import { useSession } from "./SessionProvider";
import { useSettings } from "./SettingsProvider";

// The header "Profile" menu (showUser() in the reference): avatar button and a glass panel with one row per
// licensed module, each in its module colour.
export default function AccountsMenu({ modules }: { modules: Module[] }) {
  const { session, reload, openAuth } = useSession();
  const { settings } = useSettings();
  const ref = useRef<HTMLDetailsElement>(null);
  const count = modules.filter((m) => session?.applicants[m]).length;
  const first = modules.map((m) => session?.applicants[m]).find(Boolean);
  const initials = (first?.name ?? "")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
  const pathname = usePathname();

  function close() {
    if (ref.current) ref.current.open = false;
  }

  // Closes when the visitor clicks or taps anywhere outside the menu.
  useEffect(() => {
    function outside(e: PointerEvent) {
      const menu = ref.current;
      if (menu?.open && e.target instanceof Node && !menu.contains(e.target)) menu.open = false;
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, []);

  // Closes when the page changes.
  useEffect(() => {
    if (ref.current) ref.current.open = false;
  }, [pathname]);

  function onKeyDown(e: KeyboardEvent<HTMLDetailsElement>) {
    if (e.key !== "Escape" || !ref.current?.open) return;
    close();
    ref.current.querySelector("summary")?.focus();
  }

  function auth(e: MouseEvent, mode: "in" | "up", module: Module) {
    e.preventDefault();
    close();
    openAuth({ mode, module });
  }

  async function leave(module: Module) {
    close();
    await signOut(module);
    await reload();
  }

  // Signs out of every section this visitor is signed in to (staff sign-in is not touched).
  async function leaveAll() {
    close();
    for (const m of modules) if (session?.applicants[m]) await signOut(m);
    await reload();
  }

  const avatar = (size: "sm" | "lg") => (
    <span className={"av " + size} aria-hidden="true">
      {initials || <Icon d={USER} />}
      <i className="on" />
    </span>
  );

  return (
    <details className="acm" ref={ref} onKeyDown={onKeyDown}>
      <summary className="acm-btn" aria-label={"Profile, " + count + " signed in"}>
        {avatar("sm")}
        <span className="chev" aria-hidden="true">
          <Icon d={CHEVRON} />
        </span>
      </summary>
      <div className="pop">
        <div className="acm-top">
          {avatar("lg")}
          <div>
            <b>{first?.name ?? "Profile"}</b>
            <small>
              Applicant · {count} of {modules.length} {modules.length === 1 ? "section" : "sections"}
            </small>
          </div>
        </div>
        <div className="acm-list">
          {modules.map((m) => {
            const ui = MODULE_UI[m];
            const account = session?.applicants[m];
            return (
              <div className={account ? "ar" : "ar off"} key={m} style={{ "--m": accentColour(m, settings) } as CSSProperties}>
                <span className="mi" aria-hidden="true">
                  {ui.icon}
                </span>
                {account ? (
                  <>
                    <Link className="mt" href={"/profile/" + m} onClick={close}>
                      <b>{ui.name}</b>
                      <small>ID {account.id}</small>
                    </Link>
                    <button className="ib" type="button" title={"Sign out of " + ui.name} aria-label={"Sign out of " + ui.name} onClick={() => void leave(m)}>
                      <Icon d={LOGOUT} />
                    </button>
                  </>
                ) : (
                  <div className="mt">
                    <b>{ui.name}</b>
                    <small>
                      <a href="#" onClick={(e) => auth(e, "in", m)}>
                        Sign in
                      </a>
                      {" · "}
                      <a href="#" onClick={(e) => auth(e, "up", m)}>
                        Sign up
                      </a>
                    </small>
                  </div>
                )}
              </div>
            );
          })}
        </div>
        <button className="acm-out" type="button" onClick={() => void leaveAll()}>
          <Icon d={LOGOUT} />
          Sign out
        </button>
      </div>
    </details>
  );
}

// Line icons (24px grid, drawn with the current text colour).
const USER = "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 8a7 7 0 0 1 14 0";
const CHEVRON = "m6 9 6 6 6-6";
const LOGOUT = "M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H4";

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}
