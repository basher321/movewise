"use client";

// The red banner shown when data could not be loaded (spec B10), with a Retry button.
export default function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="wrap" style={{ padding: "24px 0" }}>
      <div className="banner no" role="alert" style={{ display: "flex", gap: 12, alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>
        <span>{message}</span>
        <button className="btn ghost sm" type="button" onClick={onRetry}>
          Retry
        </button>
      </div>
    </div>
  );
}
