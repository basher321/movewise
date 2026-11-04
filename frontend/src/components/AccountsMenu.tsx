"use client";

import Link from "next/link";
import { useRef, type KeyboardEvent, type MouseEvent } from "react";
import { signOut, type Module } from "@/lib/api";
import { MODULE_UI } from "./auth/modules";
import { useSession } from "./SessionProvider";

// The header "My accounts (n)" menu (showUser() in the reference): one row per licensed module.
export default function AccountsMenu({ modules }: { modules: Module[] }) {
  const { session, reload, openAuth } = useSession();
  const ref = useRef<HTMLDetailsElement>(null);
  const count = modules.filter((m) => session?.applicants[m]).length;

  function close() {
    if (ref.current) ref.current.open = false;
  }

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
    await signOut(module);
    await reload();
  }

  return (
    <details className="acm" ref={ref} onKeyDown={onKeyDown}>
      <summary className="btn ghost sm">👤 My accounts ({count})</summary>
      <div className="pop">
        {modules.map((m) => {
          const ui = MODULE_UI[m];
          const account = session?.applicants[m];
          return (
            <div className="ar" key={m}>
              <b>
                {ui.icon} {ui.name}
              </b>
              {account ? (
                <>
                  <small>
                    {account.name} · ID {account.id}
                  </small>
                  <Link href={"/profile/" + m} onClick={close}>
                    Open profile
                  </Link>{" "}
                  ·{" "}
                  <button className="xs" type="button" onClick={() => void leave(m)}>
                    Sign out
                  </button>
                </>
              ) : (
                <>
                  <small>Not signed in</small>
                  <a href="#" onClick={(e) => auth(e, "in", m)}>
                    Sign in
                  </a>{" "}
                  ·{" "}
                  <a href="#" onClick={(e) => auth(e, "up", m)}>
                    Sign up
                  </a>
                </>
              )}
            </div>
          );
        })}
      </div>
    </details>
  );
}
