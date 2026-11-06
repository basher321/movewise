"use client";

import { useEffect, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { useSettings } from "@/components/SettingsProvider";
import {
  checkImage,
  cloneForm,
  secretOf,
  secretSaved,
  setSecret,
  takaToPoisha,
  toForm,
  validateSettings,
  type PictureKind,
  type SecretKey,
} from "@/lib/admin/settingsForm";
import {
  clearBrandingImage,
  getSettings,
  isApiError,
  saveSettings,
  sendTestEmail,
  sendTestWhatsapp,
  SMTP_SECURITY,
  uploadBrandingImage,
  type Settings,
  type SettingsInput,
  type SmtpSecurity,
} from "@/lib/api";
import { CheckField, TextField } from "./Field";
import AiProviders from "./AiProviders";
import TabPage from "./TabPage";
import type { ShowToast } from "./Toast";

// The original logo from F01, shown when Settings has no logo.
const DEFAULT_LOGO = "/logo.png";
const SAVED_SECRET = "Saved - leave empty to keep";

type F = SettingsInput;
type Text = {
  kind: "text";
  label: string;
  get: (s: F) => string;
  set: (s: F, v: string) => void;
  type?: "text" | "email" | "color" | "url";
  area?: number;
  required?: boolean;
  full?: boolean;
  placeholder?: string;
};
type Secret = { kind: "secret"; label: string; key: SecretKey; full?: boolean };
type Check = { kind: "check"; label: string; get: (s: F) => boolean; set: (s: F, v: boolean) => void };
type Def = Text | Secret | Check;

const text = (label: string, get: Text["get"], set: Text["set"], more: Partial<Text> = {}): Text => ({ kind: "text", label, get, set, ...more });
const secret = (label: string, key: SecretKey, full = false): Secret => ({ kind: "secret", label, key, full });
const check = (label: string, get: Check["get"], set: Check["set"]): Check => ({ kind: "check", label, get, set });

const stat = (i: number, part: "number" | "label"): Text =>
  text("Stat " + (i + 1) + " " + part, (s) => s.stats[i]?.[part] ?? "", (s, v) => {
    s.stats[i][part] = v;
  });

// Field lists, labels and help text from SF in aSet() of the reference.
const IDENTITY: Def[] = [
  text("Company name", (s) => s.name, (s, v) => { s.name = v; }, { required: true }),
  text("Tagline (small label on the home page)", (s) => s.tagline, (s, v) => { s.tagline = v; }),
  text("Brand colour", (s) => s.brand_color, (s, v) => { s.brand_color = v; }, { type: "color" }),
  text("Website address", (s) => s.website, (s, v) => { s.website = v; }, { placeholder: "https://…" }),
];
const WEBSITE: Def[] = [
  text("Home page headline", (s) => s.hero_title, (s, v) => { s.hero_title = v; }, { full: true }),
  text("Home page text", (s) => s.hero_text, (s, v) => { s.hero_text = v; }, { area: 2, full: true }),
  stat(0, "number"), stat(0, "label"), stat(1, "number"), stat(1, "label"), stat(2, "number"), stat(2, "label"),
  text("About page headline", (s) => s.about_title, (s, v) => { s.about_title = v; }, { full: true }),
  text("About page text", (s) => s.about_text, (s, v) => { s.about_text = v; }, { area: 3, full: true }),
];
const CONTACT: Def[] = [
  text("Address", (s) => s.address, (s, v) => { s.address = v; }, { full: true }),
  text("Phone", (s) => s.phone, (s, v) => { s.phone = v; }),
  text("Email (replies to every message go here)", (s) => s.email, (s, v) => { s.email = v; }, { type: "email" }),
  text("Office hours", (s) => s.hours, (s, v) => { s.hours = v; }),
  text("Facebook page link", (s) => s.facebook, (s, v) => { s.facebook = v; }),
];
const INVOICES: Def[] = [
  text("Invoice number prefix", (s) => s.invoice_prefix, (s, v) => { s.invoice_prefix = v; }, { required: true }),
  text("VAT BIN (optional)", (s) => s.vat_bin, (s, v) => { s.vat_bin = v; }),
  text("Invoice footer note", (s) => s.invoice_footer, (s, v) => { s.invoice_footer = v; }, { full: true }),
];
const SSL: Def[] = [
  check("Enable SSLCommerz (cards, mobile banking including Nagad, internet banking)", (s) => s.gateways.sslcommerz.enabled, (s, v) => { s.gateways.sslcommerz.enabled = v; }),
  secret("Store ID", "ssl_id"),
  secret("Store password", "ssl_pass"),
  check("Sandbox (test) mode", (s) => s.gateways.sslcommerz.sandbox, (s, v) => { s.gateways.sslcommerz.sandbox = v; }),
];
const BKASH: Def[] = [
  check("Enable bKash", (s) => s.gateways.bkash.enabled, (s, v) => { s.gateways.bkash.enabled = v; }),
  secret("App key", "bkash_key"),
  secret("App secret", "bkash_secret"),
  secret("Username", "bkash_user"),
  secret("Password", "bkash_pass"),
  check("Sandbox (test) mode", (s) => s.gateways.bkash.sandbox, (s, v) => { s.gateways.bkash.sandbox = v; }),
];
const MANUAL: Def[] = [
  check("Allow bank transfer / office payment (finance verifies it)", (s) => s.gateways.manual.enabled, (s, v) => { s.gateways.manual.enabled = v; }),
  text("Instructions shown to the payer (account number, bKash merchant number…)", (s) => s.gateways.manual.instructions, (s, v) => { s.gateways.manual.instructions = v; }, { area: 2, full: true }),
];
const EMAIL: Def[] = [
  text("Sender name", (s) => s.mail.sender_name, (s, v) => { s.mail.sender_name = v; }),
  text("Sender email address", (s) => s.mail.sender_email, (s, v) => { s.mail.sender_email = v; }, { type: "email" }),
  text("SMTP host", (s) => s.mail.smtp_host, (s, v) => { s.mail.smtp_host = v; }, { placeholder: "e.g. smtp.gmail.com" }),
  text("SMTP username", (s) => s.mail.smtp_username, (s, v) => { s.mail.smtp_username = v; }),
  secret("SMTP password", "smtp_pass"),
];
const WHATSAPP: Def[] = [
  text("WhatsApp business number (shown to people)", (s) => s.whatsapp.number, (s, v) => { s.whatsapp.number = v; }),
  text("Phone number ID (from Meta)", (s) => s.whatsapp.phone_number_id, (s, v) => { s.whatsapp.phone_number_id = v; }),
  secret("Access token", "wa_token"),
  text("Message template name", (s) => s.whatsapp.template_name, (s, v) => { s.whatsapp.template_name = v; }, { placeholder: "an approved template with one {{1}}" }),
  text("Template language", (s) => s.whatsapp.template_language, (s, v) => { s.whatsapp.template_language = v; }, { placeholder: "en or en_US" }),
  text("API version", (s) => s.whatsapp.api_version, (s, v) => { s.whatsapp.api_version = v; }, { placeholder: "v21.0" }),
];

function Section({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <h3>{title}</h3>
      {sub ? <p style={{ fontSize: 14 }}>{sub}</p> : null}
      <div style={{ marginTop: 12 }}>{children}</div>
    </div>
  );
}

// "Send test email" / "Send test WhatsApp": asks for an address and shows the result.
function TestButton({ label, ask, send }: { label: string; ask: string; send: (to: string) => Promise<{ ok: boolean; error?: string }> }) {
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    const to = window.prompt(ask)?.trim();
    if (!to) return;
    setBusy(true);
    setResult(null);
    try {
      const r = await send(to);
      setResult(r.ok ? { ok: true, text: "Sent ✓" } : { ok: false, text: r.error ?? "Not sent." });
    } catch (err) {
      setResult({ ok: false, text: isApiError(err) ? err.message : "Not sent." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="cr" style={{ margin: "12px 0 0", alignItems: "center" }}>
      <button className="btn ghost sm" type="button" disabled={busy} onClick={() => void run()}>
        {busy ? "Sending…" : label}
      </button>
      {result ? (
        <span style={{ fontSize: 14, fontWeight: 600, color: result.ok ? "#16A34A" : "#DC2626" }} role="status">
          {result.text}
        </span>
      ) : null}
    </div>
  );
}

// Settings tab (aSet() in the reference). Super admin only: anyone else sees FORBIDDEN.
export default function SettingsTab({ toast }: { toast: ShowToast }) {
  const { reload } = useSettings();
  const [stored, setStored] = useState<Settings | null>(null);
  const [form, setForm] = useState<SettingsInput | null>(null);
  const [fees, setFees] = useState({ study: "", job: "", visa: "", remote: "" });
  const [error, setError] = useState("");
  const [forbidden, setForbidden] = useState("");

  function show(s: Settings) {
    setStored(s);
    setForm(toForm(s));
    setFees({
      study: String(s.default_fee_poisha.study / 100),
      job: String(s.default_fee_poisha.job / 100),
      visa: String(s.default_fee_poisha.visa / 100),
      remote: String(s.default_fee_poisha.remote / 100),
    });
  }

  useEffect(() => {
    let live = true;
    getSettings()
      .then((s) => {
        if (live) show(s);
      })
      .catch((e: unknown) => {
        if (live) setForbidden(isApiError(e) ? e.status + " " + e.code + " - " + e.message : "Settings could not be loaded.");
      });
    return () => {
      live = false;
    };
  }, []);

  if (forbidden) return <div className="banner no">{forbidden}</div>;
  if (!stored || !form) return null;

  const patch = (change: (s: SettingsInput) => void) =>
    setForm((f) => {
      if (!f) return f;
      const next = cloneForm(f);
      change(next);
      return next;
    });

  const grid = (defs: Def[]) => (
    <div className="fgrid">
      {defs.map((d) => {
        if (d.kind === "check") return <CheckField key={d.label} label={d.label} checked={d.get(form)} onChange={(v) => patch((s) => d.set(s, v))} />;
        if (d.kind === "secret") {
          return (
            <TextField
              key={d.key}
              label={d.label}
              type="password"
              full={d.full}
              value={secretOf(form, d.key)}
              placeholder={secretSaved(stored, d.key) ? SAVED_SECRET : undefined}
              onChange={(v) => patch((s) => setSecret(s, d.key, v))}
            />
          );
        }
        return (
          <TextField
            key={d.label}
            label={d.label}
            type={d.type}
            area={d.area}
            required={d.required}
            full={d.full}
            placeholder={d.placeholder}
            value={d.get(form)}
            onChange={(v) => patch((s) => d.set(s, v))}
          />
        );
      })}
    </div>
  );

  // Pictures are saved at once; unsaved form edits stay in the form.
  async function picture(kind: PictureKind, file: File | null) {
    try {
      const saved = file ? await uploadBrandingImage(kind, file) : await clearBrandingImage(kind);
      setStored(saved);
      await reload();
      toast(file ? "Picture saved." : "Picture removed.");
    } catch (e) {
      toast(isApiError(e) ? e.message : "The picture could not be saved.", true);
    }
  }

  async function upload(kind: PictureKind, e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const problem = checkImage(file, kind);
    if (problem) {
      toast(problem, true);
      return;
    }
    await picture(kind, file);
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!stored || !form) return;
    const next = cloneForm(form);
    next.default_fee_poisha = {
      study: takaToPoisha(fees.study),
      job: takaToPoisha(fees.job),
      visa: takaToPoisha(fees.visa),
      remote: takaToPoisha(fees.remote),
    };
    next.invoice_prefix = next.invoice_prefix.trim();
    const problem = validateSettings(next, stored);
    if (problem) {
      setError(problem);
      return;
    }
    try {
      show(await saveSettings(next));
      setError("");
      await reload();
      toast("Settings saved.");
    } catch (err) {
      setError(isApiError(err) ? err.message : "Settings could not be saved.");
    }
  }

  const pictureLabel = { display: "block", fontSize: 13, fontWeight: 700, color: "var(--muted)", marginBottom: 6 } as const;

  return (
    <TabPage
      title="Settings"
      sub="Shown on the website, invoices, certificates and in every email."
      actions={
        <button className="btn sm" form="setf" type="submit">
          Save settings
        </button>
      }
    >
      <form id="setf" noValidate onSubmit={submit}>
        <Section title="Company identity">
          {grid(IDENTITY)}
          <div className="fgrid" style={{ marginTop: 6 }}>
            <div>
              <span style={pictureLabel}>Logo (PNG, JPEG or WebP, max 500 KB)</span>
              <div className="cr" style={{ margin: 0, alignItems: "center" }}>
                {/* eslint-disable-next-line @next/next/no-img-element -- the uploaded logo, served by the backend */}
                <img className="prev" src={stored.logo_url || DEFAULT_LOGO} alt={stored.logo_url ? "Logo" : "Current logo"} />
                <label className="btn ghost sm">
                  Upload
                  <input type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={(e) => void upload("logo", e)} />
                </label>
                {stored.logo_url ? (
                  <button type="button" className="lk r" onClick={() => void picture("logo", null)}>
                    Use default
                  </button>
                ) : null}
              </div>
            </div>
            <div>
              <span style={pictureLabel}>Home page picture (max 1.5 MB)</span>
              <div className="cr" style={{ margin: 0, alignItems: "center" }}>
                {stored.hero_url ? (
                  // eslint-disable-next-line @next/next/no-img-element -- the uploaded picture, served by the backend
                  <img className="hprev" src={stored.hero_url} alt="Home picture" />
                ) : (
                  <span style={{ color: "var(--muted)", fontSize: 14 }}>None (the tracking card is shown)</span>
                )}
                <label className="btn ghost sm">
                  Upload
                  <input type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={(e) => void upload("hero", e)} />
                </label>
                {stored.hero_url ? (
                  <button type="button" className="lk r" onClick={() => void picture("hero", null)}>
                    Remove
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        </Section>
        <Section title="Website text" sub="Leave a stat empty to hide it. Use only real numbers about your company.">
          {grid(WEBSITE)}
        </Section>
        <Section title="Contact details" sub="Shown on the Contact page, footer and invoices.">
          {grid(CONTACT)}
        </Section>
        <Section title="Invoices and default fees">
          {grid(INVOICES)}
          <div className="fgrid" style={{ marginTop: 6 }}>
            <TextField label="Default student application fee (৳)" required value={fees.study} onChange={(v) => setFees({ ...fees, study: v })} />
            <TextField label="Default job application fee (৳)" required value={fees.job} onChange={(v) => setFees({ ...fees, job: v })} />
            <TextField label="Default immigration application fee (৳)" required value={fees.visa} onChange={(v) => setFees({ ...fees, visa: v })} />
            <TextField label="Default remote job application fee (৳)" required value={fees.remote} onChange={(v) => setFees({ ...fees, remote: v })} />
          </div>
          <p className="sub" style={{ margin: "8px 0 0", fontSize: 13 }}>
            Used for every university, job, visa programme or remote job without its own fee (set those in the Fees tab).
          </p>
        </Section>
        <Section title="Payment gateways" sub="Money goes straight to your own merchant account. Keys are stored encrypted on the server and never shown again.">
          <h4 style={{ margin: "0 0 10px" }}>SSLCommerz</h4>
          {grid(SSL)}
          <h4 style={{ margin: "18px 0 10px" }}>bKash</h4>
          {grid(BKASH)}
          <h4 style={{ margin: "18px 0 10px" }}>Offline payment</h4>
          {grid(MANUAL)}
        </Section>
        <Section title="Email" sub="Without these, emails wait as “Queued” in Notifications. Codes, receipts and updates are sent from this address.">
          {grid(EMAIL)}
          <div className="fgrid" style={{ marginTop: 6 }}>
            <TextField
              label="SMTP port"
              value={String(form.mail.smtp_port)}
              onChange={(v) => patch((s) => { s.mail.smtp_port = /^\d+$/.test(v) ? Number(v) : 0; })}
            />
            <label className="fl">
              <span>Security</span>
              <select value={form.mail.smtp_security} onChange={(e) => patch((s) => { s.mail.smtp_security = e.target.value as SmtpSecurity; })}>
                {SMTP_SECURITY.map((x) => (
                  <option key={x} value={x}>
                    {x === "starttls" ? "STARTTLS (port 587)" : x === "ssl" ? "SSL/TLS (port 465)" : "None (not recommended)"}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <TestButton label="Send test email" ask="Send a test email to which address?" send={sendTestEmail} />
          <p className="sub" style={{ margin: "6px 0 0", fontSize: 13 }}>Save your settings first; the test uses the saved ones.</p>
        </Section>
        <Section title="WhatsApp" sub="WhatsApp Cloud API by Meta. Messages are sent with your approved template; without these they wait as “Queued”.">
          {grid(WHATSAPP)}
          <TestButton label="Send test WhatsApp" ask="Send a test WhatsApp to which mobile number?" send={sendTestWhatsapp} />
        </Section>
        {form.ai ? (
          <Section
            title="AI assistants"
            sub="The Student Consultancy, Job Processing, Immigration and Remote Jobs advisors answer only from your published universities, jobs, visa programmes, remote jobs and fees, each about its own section only. Providers are always tried in this order: Claude, ChatGPT, Gemini, Groq. If one fails, or gives a number that is not in your data, the next one answers. If none works, the built-in replies from your data are used."
          >
            <AiProviders ai={form.ai} stored={stored} onChange={(ai) => patch((s) => { s.ai = ai; })} />
          </Section>
        ) : null}
        <p className="err" role="alert" id="serr">
          {error}
        </p>
        <button className="btn" type="submit">
          Save settings
        </button>
      </form>
    </TabPage>
  );
}
