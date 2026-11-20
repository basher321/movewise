import Link from "next/link";
import type { Module } from "@/lib/api";
import { CV_TEXT } from "./strings";

// B28: "Build my CV with AI" next to the existing agent of a service. Opens the one CV Agent page,
// in the account of this service.
export default function CvAgentCard({ module, text }: { module: Module; text: string }) {
  return (
    <div className="card" style={{ marginTop: 22, display: "flex", gap: 18, alignItems: "center", flexWrap: "wrap" }}>
      <div style={{ fontSize: 38 }} aria-hidden>
        📄
      </div>
      <div style={{ flex: "1 1 260px", minWidth: 0 }}>
        <span className="tag">🤖 {CV_TEXT.product}</span>
        <h3 style={{ margin: "8px 0 4px" }}>Build my CV with AI</h3>
        <p style={{ margin: 0 }}>{text}</p>
        <div className="ch" style={{ margin: "10px 0 0" }}>
          {CV_TEXT.badges.map((b) => (
            <span className="y" key={b}>
              ✓ {b}
            </span>
          ))}
        </div>
      </div>
      <Link className="btn" href={"/cv-agent?from=" + module}>
        Build my CV →
      </Link>
    </div>
  );
}
