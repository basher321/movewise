// The username rule, the same as the server (backend/app/auth/inputs.py): 3 to 30 of a-z, 0-9,
// "." and "_", compared in lower case. Used by the sign-up form to say exactly what is wrong,
// and to offer a fixed version, before anything is sent.

const ALLOWED = /^[a-z0-9._]{3,30}$/;
const MIN = 3;
const MAX = 30;

export type UsernameCheck = {
  // What is wrong, in plain words; null when the username is fine.
  problem: string | null;
  // A username that follows the rule, made from what was typed; null when none can be made
  // or it is the same as what was typed.
  suggestion: string | null;
};

export function suggestUsername(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/@.*$/, "")
    .replace(/[\s-]+/g, "_")
    .replace(/[^a-z0-9._]/g, "")
    .slice(0, MAX);
}

export function checkUsername(raw: string): UsernameCheck {
  const value = raw.trim().toLowerCase();
  if (!value) return { problem: null, suggestion: null };
  if (ALLOWED.test(value)) return { problem: null, suggestion: null };

  const fixed = suggestUsername(raw);
  const suggestion = ALLOWED.test(fixed) && fixed !== value ? fixed : null;

  let problem: string;
  if (value.includes("@")) {
    problem = "A username is not an email. Use only letters, numbers, . or _ (no @).";
  } else if (/\s/.test(value)) {
    problem = "A username cannot have spaces. Use _ or . instead.";
  } else {
    const bad = Array.from(new Set(Array.from(value).filter((c) => !/[a-z0-9._]/.test(c))));
    if (bad.length > 0) {
      const list = bad.slice(0, 5).map((c) => `"${c}"`).join(" ");
      problem = `${list} cannot be used. Use only English letters, numbers, . or _.`;
    } else if (value.length < MIN) {
      problem = `A username needs at least ${MIN} characters.`;
    } else {
      problem = `A username can have at most ${MAX} characters.`;
    }
  }
  return { problem, suggestion };
}
