import type { ReactNode } from "react";
import Button from "./Button";

type EmptyStateProps = {
  title: string;
  children?: ReactNode;
  action?: { label: string; href: string };
};

export default function EmptyState({ title, children, action }: EmptyStateProps) {
  return (
    <div className="card">
      <h3>{title}</h3>
      {children ? <p>{children}</p> : null}
      {action ? (
        <div className="acts" style={{ marginTop: 20 }}>
          <Button href={action.href}>{action.label}</Button>
        </div>
      ) : null}
    </div>
  );
}
