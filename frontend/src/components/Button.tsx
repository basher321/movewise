import Link from "next/link";
import type { ReactNode } from "react";

type ButtonProps = {
  variant?: "primary" | "ghost";
  size?: "md" | "sm";
  href?: string;
  onClick?: () => void;
  children: ReactNode;
};

export default function Button({ variant = "primary", size = "md", href, onClick, children }: ButtonProps) {
  const className = ["btn", variant === "ghost" && "ghost", size === "sm" && "sm"].filter(Boolean).join(" ");
  if (href) {
    return (
      <Link className={className} href={href}>
        {children}
      </Link>
    );
  }
  return (
    <button className={className} type="button" onClick={onClick}>
      {children}
    </button>
  );
}
