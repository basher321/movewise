"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

export type ShowToast = (message: string, bad?: boolean) => void;

// The reference #xtoast: a short message at the bottom of the screen.
export function useToast(): { toast: ShowToast; toastNode: ReactNode } {
  const [state, setState] = useState<{ message: string; bad: boolean; at: number } | null>(null);

  useEffect(() => {
    if (!state) return;
    const timer = setTimeout(() => setState(null), 3400);
    return () => clearTimeout(timer);
  }, [state]);

  const toast = useCallback<ShowToast>((message, bad = false) => setState({ message, bad, at: Date.now() }), []);

  const className = state ? "show" + (state.bad ? " bad" : "") : "";
  const toastNode = (
    <div id="xtoast" role="status" aria-live="polite" className={className}>
      {state?.message}
    </div>
  );
  return { toast, toastNode };
}
