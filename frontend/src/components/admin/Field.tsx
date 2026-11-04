"use client";

import type { CSSProperties } from "react";

// Form fields in the reference fhtml() style: .fl label with a small heading, .simf for checkboxes.

const FULL: CSSProperties = { gridColumn: "1/-1" };

type TextFieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: "text" | "email" | "password" | "color" | "url";
  area?: number; // rows, for a textarea
  required?: boolean;
  full?: boolean;
  placeholder?: string;
  autoComplete?: string;
};

export function TextField({ label, value, onChange, type = "text", area, required, full, placeholder, autoComplete }: TextFieldProps) {
  return (
    <label className="fl" style={full ? FULL : undefined}>
      <span>
        {label}
        {required ? " *" : ""}
      </span>
      {area ? (
        <textarea rows={area} style={{ minHeight: 0 }} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input
          type={type}
          value={value}
          placeholder={placeholder}
          autoComplete={autoComplete ?? (type === "password" ? "new-password" : undefined)}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </label>
  );
}

type CheckFieldProps = {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
};

export function CheckField({ label, checked, onChange }: CheckFieldProps) {
  return (
    <label className="simf" style={FULL}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} /> {label}
    </label>
  );
}
