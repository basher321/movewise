import type { ReactNode } from "react";

type TabPageProps = {
  title: string;
  sub: string;
  actions?: ReactNode;
  children: ReactNode;
};

// The heading of an admin tab (page() in the reference): title, actions on the right, short description.
export default function TabPage({ title, sub, actions, children }: TabPageProps) {
  return (
    <>
      <div className="top" style={{ alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
        <h3 style={{ fontSize: 24 }}>{title}</h3>
        <div className="cr" style={{ margin: 0 }}>
          {actions}
        </div>
      </div>
      <p style={{ color: "var(--muted)", margin: "0 0 18px" }}>{sub}</p>
      {children}
    </>
  );
}
