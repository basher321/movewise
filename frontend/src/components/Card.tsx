import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";
import type { Accent } from "./PageShell";

type CardProps = {
  href?: string;
  accent?: Accent;
  className?: string;
  children?: ReactNode;
};

export default function Card({ href, accent, className, children }: CardProps) {
  const cls = className ? `card ${className}` : "card";
  const style = accent ? ({ "--a": accent } as CSSProperties) : undefined;
  if (href) {
    return (
      <Link className={cls} href={href} style={style}>
        {children}
      </Link>
    );
  }
  return (
    <div className={cls} style={style}>
      {children}
    </div>
  );
}
