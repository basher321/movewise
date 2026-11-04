import type { ReactNode } from "react";
import ModuleGate from "@/components/ModuleGate";

// Every page under /courses belongs to the course module.
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <ModuleGate module="course" accent="brand">
      {children}
    </ModuleGate>
  );
}
