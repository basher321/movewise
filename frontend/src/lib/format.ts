// Formats a whole number of poisha as taka, e.g. 1200000 -> "৳12,000".
export function formatMoney(amount_poisha: number): string {
  const sign = amount_poisha < 0 ? "-" : "";
  const abs = Math.abs(amount_poisha);
  const taka = Math.floor(abs / 100);
  const rest = abs % 100;
  return sign + "৳" + taka.toLocaleString("en-US") + (rest ? "." + String(rest).padStart(2, "0") : "");
}

// Shows an ISO date in Asia/Dhaka, e.g. "25 Oct 2026" (short) or "25 October 2026" (long).
export function formatDate(iso: string, month: "short" | "long" = "short"): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month, year: "numeric", timeZone: "Asia/Dhaka" });
}

// Shows an ISO date and time in Asia/Dhaka, e.g. "25 Oct 2026, 12:00" (fdt() in the reference).
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Dhaka" });
}
