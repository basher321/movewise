import { isApiError } from "@/lib/api";

const FALLBACK = "Something went wrong. Please try again.";

// The text for the error line of the sign-in / sign-up dialog.
export function authMessage(error: unknown, step: "in" | "up"): string {
  if (!isApiError(error)) return FALLBACK;
  if (step === "in" && error.code === "UNAUTHENTICATED") return "Wrong username or password.";
  return error.message;
}

// The text for the error line of other forms.
export function errorText(error: unknown): string {
  return isApiError(error) ? error.message : FALLBACK;
}

// B15: the answer after asking for a reset link (it never says whether the account exists).
export const LINK_SENT = "If this account exists and has an email, we have sent a link to reset the password. It works once, for 30 minutes.";
