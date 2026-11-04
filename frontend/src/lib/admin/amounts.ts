// Turns typed amounts into whole numbers without floats (B16): taka -> poisha, percent -> basis points.
// Both accept digits with at most two decimals and optional thousands commas; anything else is null.

function hundredths(text: string): number | null {
  const clean = text.trim().replace(/,/g, "");
  const m = /^(\d{1,12})(?:\.(\d{1,2}))?$/.exec(clean);
  if (!m) return null;
  return Number(m[1]) * 100 + Number((m[2] ?? "").padEnd(2, "0"));
}

export const takaToPoisha = (text: string): number | null => hundredths(text);

export function percentToBp(text: string): number | null {
  const bp = hundredths(text);
  return bp === null || bp > 10000 ? null : bp;
}

// For form fields: 150050 -> "1500.50", 1250 -> "12.5".
export function poishaToText(poisha: number): string {
  const rest = poisha % 100;
  return String(Math.floor(poisha / 100)) + (rest ? "." + String(rest).padStart(2, "0") : "");
}

export function bpToText(bp: number): string {
  const rest = bp % 100;
  return String(Math.floor(bp / 100)) + (rest ? "." + String(rest).padStart(2, "0").replace(/0$/, "") : "");
}
