import type { ReactNode } from "react";
import ModuleGate from "@/components/ModuleGate";

// Every page under /jobs belongs to the job module.
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <ModuleGate module="job" accent="#D97706">
      {children}
    </ModuleGate>
  );
}
