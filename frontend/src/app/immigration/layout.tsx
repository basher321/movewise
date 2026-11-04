import type { ReactNode } from "react";
import ModuleGate from "@/components/ModuleGate";

// Every page under /immigration belongs to the visa module (B19).
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <ModuleGate module="visa" accent="#E11D48">
      {children}
    </ModuleGate>
  );
}
