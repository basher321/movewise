import type { ReactNode } from "react";

type BadgeProps = {
  tone?: "default" | "ok" | "warn" | "no" | "info";
  children: ReactNode;
};

export default function Badge({ tone = "default", children }: BadgeProps) {
  return <span className={tone === "default" ? "bd" : `bd ${tone}`}>{children}</span>;
}
