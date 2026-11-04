import type { ReactNode } from "react";
import ModuleGate from "@/components/ModuleGate";

// Every page under /verify belongs to the course module.
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <ModuleGate module="course" accent="#4F46E5">
      {children}
    </ModuleGate>
  );
}
