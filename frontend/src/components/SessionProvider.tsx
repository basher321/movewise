"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { getSession, type Module, type Session } from "@/lib/api";
import AuthDialog from "./auth/AuthDialog";

export type AuthRequest = {
  mode: "in" | "up";
  module?: Module;
  // Replaces the line under the title until the person switches section or mode.
  note?: string;
  // Runs once the person is signed in and verified.
  after?: () => void;
};

type SessionContextValue = {
  session: Session | null; // null until loaded
  reload: () => Promise<void>;
  openAuth: (request: AuthRequest) => void;
};

const SessionContext = createContext<SessionContextValue>({
  session: null,
  reload: async () => {},
  openAuth: () => {},
});

export function useSession(): SessionContextValue {
  return useContext(SessionContext);
}

// Loads the session once at app start and holds the Sign in / Sign up dialog.
// The header, profile and later pages read sessions only from here.
export default function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [auth, setAuth] = useState<(AuthRequest & { seq: number }) | null>(null);
  const seq = useRef(0);

  const reload = useCallback(async () => {
    setSession(await getSession());
  }, []);

  useEffect(() => {
    let live = true;
    getSession()
      .then((s) => {
        if (live) setSession(s);
      })
      .catch(() => {
        // Server not reachable: treat as signed out; the settings banner explains the problem.
        if (live) setSession({ admin: null, applicants: {} });
      });
    return () => {
      live = false;
    };
  }, []);

  const openAuth = useCallback((request: AuthRequest) => {
    seq.current += 1;
    setAuth({ ...request, seq: seq.current });
  }, []);

  const close = useCallback(() => setAuth(null), []);

  const signedIn = useCallback(async () => {
    const after = auth?.after;
    setAuth(null);
    await reload();
    after?.();
  }, [auth, reload]);

  return (
    <SessionContext.Provider value={{ session, reload, openAuth }}>
      {children}
      {auth ? <AuthDialog key={auth.seq} request={auth} onClose={close} onSignedIn={signedIn} /> : null}
    </SessionContext.Provider>
  );
}
