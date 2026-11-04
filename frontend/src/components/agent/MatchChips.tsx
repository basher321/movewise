import type { MatchCheck } from "@/lib/api";

// The green and red condition chips (chip() in the reference).
export default function MatchChips({ checks }: { checks: MatchCheck[] }) {
  return (
    <div className="ch">
      {checks.map((c) => (
        <span className={c.ok ? "y" : "n"} key={c.label}>
          {c.ok ? "✓ " : "✗ "}
          {c.label}
        </span>
      ))}
    </div>
  );
}
