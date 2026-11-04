import type { ReactNode } from "react";

export default function Tag({ children }: { children: ReactNode }) {
  return <span className="tag">{children}</span>;
}
