// Settings form rules: secret fields, validation and picture checks (from aSet() in the reference).
// Secrets never come back from the server: the form starts with them empty, an empty secret keeps
// the saved value, and the server only says whether each one is saved.

import { AI_PROVIDERS, type Settings, type SettingsInput } from "../api";

const EMAIL_RE = /^\S+@\S+\.\S+$/;

export const LOGO_MAX_BYTES = 500 * 1024;
export const HERO_MAX_BYTES = 1.5 * 1024 * 1024;

interface SecretField {
  get(s: SettingsInput): string;
  set(s: SettingsInput, value: string): void;
  saved(s: Settings): boolean;
}

const SECRETS = {
  ssl_id: {
    get: (s) => s.gateways.sslcommerz.store_id,
    set: (s, v) => { s.gateways.sslcommerz.store_id = v; },
    saved: (s) => s.gateways.sslcommerz.store_id.saved,
  },
  ssl_pass: {
    get: (s) => s.gateways.sslcommerz.store_password,
    set: (s, v) => { s.gateways.sslcommerz.store_password = v; },
    saved: (s) => s.gateways.sslcommerz.store_password.saved,
  },
  bkash_key: {
    get: (s) => s.gateways.bkash.app_key,
    set: (s, v) => { s.gateways.bkash.app_key = v; },
    saved: (s) => s.gateways.bkash.app_key.saved,
  },
  bkash_secret: {
    get: (s) => s.gateways.bkash.app_secret,
    set: (s, v) => { s.gateways.bkash.app_secret = v; },
    saved: (s) => s.gateways.bkash.app_secret.saved,
  },
  bkash_user: {
    get: (s) => s.gateways.bkash.username,
    set: (s, v) => { s.gateways.bkash.username = v; },
    saved: (s) => s.gateways.bkash.username.saved,
  },
  bkash_pass: {
    get: (s) => s.gateways.bkash.password,
    set: (s, v) => { s.gateways.bkash.password = v; },
    saved: (s) => s.gateways.bkash.password.saved,
  },
  smtp_pass: {
    get: (s) => s.mail.smtp_password,
    set: (s, v) => { s.mail.smtp_password = v; },
    saved: (s) => s.mail.smtp_password.saved,
  },
  wa_token: {
    get: (s) => s.whatsapp.token,
    set: (s, v) => { s.whatsapp.token = v; },
    saved: (s) => s.whatsapp.token.saved,
  },
} satisfies Record<string, SecretField>;

export type SecretKey = keyof typeof SECRETS;

export function cloneForm(s: SettingsInput): SettingsInput {
  return JSON.parse(JSON.stringify(s)) as SettingsInput;
}

export function secretOf(form: SettingsInput, key: SecretKey): string {
  return SECRETS[key].get(form);
}

export function setSecret(form: SettingsInput, key: SecretKey, value: string): void {
  SECRETS[key].set(form, value);
}

export function secretSaved(stored: Settings, key: SecretKey): boolean {
  return SECRETS[key].saved(stored);
}

// The form for the stored settings: every secret empty (an empty secret keeps the saved value).
export function toForm(s: Settings): SettingsInput {
  const g = s.gateways;
  return {
    name: s.name,
    tagline: s.tagline,
    brand_color: s.brand_color,
    hero_title: s.hero_title,
    hero_text: s.hero_text,
    stats: [0, 1, 2].map((i) => ({ number: s.stats[i]?.number ?? "", label: s.stats[i]?.label ?? "" })),
    about_title: s.about_title,
    about_text: s.about_text,
    address: s.address,
    phone: s.phone,
    email: s.email,
    hours: s.hours,
    facebook: s.facebook,
    website: s.website,
    invoice_prefix: s.invoice_prefix,
    invoice_footer: s.invoice_footer,
    vat_bin: s.vat_bin,
    default_fee_poisha: { ...s.default_fee_poisha },
    gateways: {
      sslcommerz: { enabled: g.sslcommerz.enabled, sandbox: g.sslcommerz.sandbox, store_id: "", store_password: "" },
      bkash: { enabled: g.bkash.enabled, sandbox: g.bkash.sandbox, app_key: "", app_secret: "", username: "", password: "" },
      // Nagad is paid inside SSLCommerz; its own section is not shown and stays as stored.
      nagad: { enabled: g.nagad.enabled, sandbox: g.nagad.sandbox, merchant_id: "", private_key: "" },
      manual: { ...g.manual },
    },
    mail: {
      sender_name: s.mail.sender_name,
      sender_email: s.mail.sender_email,
      smtp_host: s.mail.smtp_host,
      smtp_port: s.mail.smtp_port,
      smtp_security: s.mail.smtp_security,
      smtp_username: s.mail.smtp_username,
      smtp_password: "",
      webmail_url: s.mail.webmail_url,
    },
    whatsapp: {
      number: s.whatsapp.number,
      token: "",
      phone_number_id: s.whatsapp.phone_number_id,
      template_name: s.whatsapp.template_name,
      template_language: s.whatsapp.template_language,
      api_version: s.whatsapp.api_version,
    },
    // B17: keys start empty (an empty key keeps the saved one).
    ai: {
      order: [...AI_PROVIDERS],
      providers: Object.fromEntries(
        AI_PROVIDERS.map((p) => [p, { enabled: s.ai.providers[p].enabled, model: s.ai.providers[p].model, key: "" }]),
      ) as NonNullable<SettingsInput["ai"]>["providers"],
    },
  };
}

export const AI_LABELS: Record<(typeof AI_PROVIDERS)[number], string> = { claude: "Claude", openai: "ChatGPT", gemini: "Gemini", groq: "Groq" };

// B17: the first AI settings problem, or null.
export function validateAi(form: SettingsInput, stored: Settings): string | null {
  if (!form.ai) return null;
  for (const p of AI_PROVIDERS) {
    const item = form.ai.providers[p];
    const model = item.model.trim();
    if (model && !/^[A-Za-z0-9._:/-]{1,100}$/.test(model)) return AI_LABELS[p] + " model may use letters, digits and . _ : / - only.";
    if (item.enabled && !model) return AI_LABELS[p] + " needs a model name.";
    if (item.enabled && !item.key.trim() && !stored.ai.providers[p].key.saved) return AI_LABELS[p] + " needs an API key.";
  }
  return null;
}

function missingList(names: string[]): string {
  return names.length === 1 ? names[0] : names.slice(0, -1).join(", ") + " and " + names[names.length - 1];
}

// Returns the first error, or null when the settings may be saved. The server checks again.
export function validateSettings(form: SettingsInput, stored: Settings): string | null {
  if (!form.name.trim()) return "Please fill in: Company name.";
  if (!/^#[0-9A-Fa-f]{6}$/.test(form.brand_color)) return "Brand colour must look like #4F46E5.";
  if (!/^[A-Za-z0-9]{1,10}$/.test(form.invoice_prefix.trim())) return "Invoice number prefix must be 1 to 10 letters or digits.";
  if (form.email.trim() && !EMAIL_RE.test(form.email.trim())) return "Please enter a valid email.";
  if (form.mail.sender_email.trim() && !EMAIL_RE.test(form.mail.sender_email.trim())) return "Please enter a valid sender email address.";
  const fees = form.default_fee_poisha;
  if ([fees.study, fees.job, fees.visa, fees.remote].some((f) => !Number.isInteger(f) || f <= 0)) {
    return "Default fees must be whole taka above 0.";
  }
  if (!Number.isInteger(form.mail.smtp_port) || form.mail.smtp_port < 1 || form.mail.smtp_port > 65535) return "SMTP port must be from 1 to 65535.";
  const webmail = form.mail.webmail_url.trim();
  if (webmail && (!webmail.startsWith("https://") || /\s/.test(webmail))) {
    return "The webmail link must start with https:// (for example https://webmail.example.com).";
  }
  const g = form.gateways;
  if (!g.sslcommerz.enabled && !g.bkash.enabled && !g.nagad.enabled && !g.manual.enabled) return "Turn on at least one payment method.";
  const need = (gateway: string, fields: [string, SecretKey][]): string | null => {
    const missing = fields.filter(([, key]) => !secretOf(form, key).trim() && !secretSaved(stored, key)).map(([label]) => label);
    return missing.length ? gateway + " is turned on: please fill in " + missingList(missing) + "." : null;
  };
  if (g.sslcommerz.enabled) {
    const e = need("SSLCommerz", [["Store ID", "ssl_id"], ["Store password", "ssl_pass"]]);
    if (e) return e;
  }
  if (g.bkash.enabled) {
    const e = need("bKash", [["App key", "bkash_key"], ["App secret", "bkash_secret"], ["Username", "bkash_user"], ["Password", "bkash_pass"]]);
    if (e) return e;
  }
  return validateAi(form, stored);
}

export type PictureKind = "logo" | "hero";

// PNG, JPEG or WebP; logo max 500 KB, home picture max 1.5 MB. The server checks the real type.
export function checkImage(file: { type: string; size: number }, kind: PictureKind): string | null {
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) return "Please choose a PNG, JPEG or WebP picture.";
  if (kind === "logo" && file.size > LOGO_MAX_BYTES) return "File is too large (max 500 KB).";
  if (kind === "hero" && file.size > HERO_MAX_BYTES) return "File is too large (max 1.5 MB).";
  return null;
}

// Whole taka typed in a box -> poisha, or NaN when it is not a whole number.
export function takaToPoisha(text: string): number {
  return /^\d+$/.test(text.trim()) ? Number(text.trim()) * 100 : Number.NaN;
}
