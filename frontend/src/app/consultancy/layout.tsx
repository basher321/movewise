import type { ReactNode } from "react";
import ModuleGate from "@/components/ModuleGate";

// Every page under /consultancy belongs to the study module.
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <ModuleGate module="study" accent="#0EA5A4">
      {children}
    </ModuleGate>
  );
}
