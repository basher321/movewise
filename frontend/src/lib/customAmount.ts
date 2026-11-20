// B27: the amount of a custom payment, typed in whole taka. The server checks the same rules.

export const MIN_CUSTOM_POISHA = 100 * 100; // 100 taka
export const MAX_CUSTOM_POISHA = 1_000_000 * 100; // 1,000,000 taka

// "25000" or "25,000" -> 2500000 poisha; anything else -> an error message for the form.
export function parseCustomAmount(input: string): { poisha: number } | { error: string } {
  const digits = input.trim().replace(/,/g, "");
  if (!digits) return { error: "Please enter the amount in taka." };
  if (!/^\d+$/.test(digits)) return { error: "The amount must be a whole number of taka (no poisha)." };
  const poisha = Number(digits) * 100;
  if (poisha < MIN_CUSTOM_POISHA || poisha > MAX_CUSTOM_POISHA) {
    return { error: "The amount must be between ৳100 and ৳1,000,000." };
  }
  return { poisha };
}
