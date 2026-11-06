import type { ReactNode } from "react";
import ModuleGate from "@/components/ModuleGate";

// Every page under /remote-jobs belongs to the Remote Jobs module.
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <ModuleGate module="remote" accent="#059669">
      {children}
    </ModuleGate>
  );
}
