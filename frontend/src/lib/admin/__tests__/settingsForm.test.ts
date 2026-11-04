import { describe, expect, it } from "vitest";
import type { Settings } from "../../api";
import { checkImage, secretSaved, setSecret, takaToPoisha, toForm, validateSettings } from "../settingsForm";

const no = { saved: false };
const yes = { saved: true };

function stored(changes: Partial<Settings> = {}): Settings {
  return {
    name: "Agency",
    tagline: "",
    brand_color: "#4F46E5",
    logo_url: null,
    hero_url: null,
    hero_title: "",
    hero_text: "",
    stats: [],
    about_title: "",
    about_text: "",
    address: "",
    phone: "",
    email: "",
    hours: "",
    facebook: "",
    website: "",
    invoice_prefix: "INV",
    invoice_footer: "",
    vat_bin: "",
    default_fee_poisha: { study: 100000, job: 150000, visa: 120000 },
    gateways: {
      sslcommerz: { enabled: false, sandbox: true, store_id: no, store_password: no },
      bkash: { enabled: false, sandbox: true, app_key: no, app_secret: no, username: no, password: no },
      nagad: { enabled: false, sandbox: true, merchant_id: no, private_key: no },
      manual: { enabled: true, instructions: "" },
    },
    mail: { sender_name: "", sender_email: "", smtp_host: "", smtp_port: 587, smtp_security: "starttls", smtp_username: "", smtp_password: no },
    whatsapp: { number: "", token: no, phone_number_id: "", template_name: "", template_language: "en", api_version: "v21.0" },
    ai: {
      order: ["claude", "openai", "gemini", "groq"],
      providers: {
        claude: { enabled: false, model: "claude-opus-5-5", key: no },
        openai: { enabled: false, model: "", key: no },
        gemini: { enabled: false, model: "", key: no },
        groq: { enabled: false, model: "", key: yes },
      },
    },
    ...changes,
  };
}

describe("settings form", () => {
  it("B17: AI keys start empty; an enabled provider needs a model and a key", () => {
    const s = stored();
    const form = toForm(s);
    expect(form.ai?.providers.claude).toEqual({ enabled: false, model: "claude-opus-5-5", key: "" });
    form.ai!.providers.openai.enabled = true;
    expect(validateSettings(form, s)).toBe("ChatGPT needs a model name.");
    form.ai!.providers.openai.model = "gpt test";
    expect(validateSettings(form, s)).toBe("ChatGPT model may use letters, digits and . _ : / - only.");
    form.ai!.providers.openai.model = "gpt-test";
    expect(validateSettings(form, s)).toBe("ChatGPT needs an API key.");
    form.ai!.providers.openai.key = "sk-typed";
    expect(validateSettings(form, s)).toBeNull();
    form.ai!.providers.groq = { enabled: true, model: "llama-test", key: "" };
    expect(validateSettings(form, s)).toBeNull(); // saved key is kept
  });


  it("starts with every secret empty and three stats", () => {
    const form = toForm(stored({ gateways: { ...stored().gateways, sslcommerz: { enabled: true, sandbox: true, store_id: yes, store_password: yes } } }));
    expect(form.gateways.sslcommerz.store_id).toBe("");
    expect(form.mail.smtp_password).toBe("");
    expect(form.stats).toHaveLength(3);
  });

  it("accepts a valid form", () => {
    const s = stored();
    expect(validateSettings(toForm(s), s)).toBeNull();
  });

  it("asks for gateway secrets that are neither typed nor saved", () => {
    const s = stored();
    const form = toForm(s);
    form.gateways.sslcommerz.enabled = true;
    expect(validateSettings(form, s)).toBe("SSLCommerz is turned on: please fill in Store ID and Store password.");
    setSecret(form, "ssl_id", "store");
    setSecret(form, "ssl_pass", "pass");
    expect(validateSettings(form, s)).toBeNull();
  });

  it("accepts saved gateway secrets left empty", () => {
    const s = stored({ gateways: { ...stored().gateways, bkash: { enabled: true, sandbox: true, app_key: yes, app_secret: yes, username: yes, password: yes } } });
    expect(secretSaved(s, "bkash_key")).toBe(true);
    expect(validateSettings(toForm(s), s)).toBeNull();
  });

  it("needs a payment method, valid fees and a valid prefix", () => {
    const s = stored();
    const form = toForm(s);
    form.gateways.manual.enabled = false;
    expect(validateSettings(form, s)).toBe("Turn on at least one payment method.");
    const fees = toForm(s);
    fees.default_fee_poisha.study = takaToPoisha("12.5");
    expect(validateSettings(fees, s)).toBe("Default fees must be whole taka above 0.");
    const prefix = toForm(s);
    prefix.invoice_prefix = "INV-2026";
    expect(validateSettings(prefix, s)).toBe("Invoice number prefix must be 1 to 10 letters or digits.");
  });

  it("converts whole taka to poisha", () => {
    expect(takaToPoisha("1200")).toBe(120000);
    expect(Number.isNaN(takaToPoisha("12.50"))).toBe(true);
  });

  it("checks pictures by type and size", () => {
    expect(checkImage({ type: "image/gif", size: 10 }, "logo")).toBe("Please choose a PNG, JPEG or WebP picture.");
    expect(checkImage({ type: "image/png", size: 600 * 1024 }, "logo")).toBe("File is too large (max 500 KB).");
    expect(checkImage({ type: "image/jpeg", size: 600 * 1024 }, "hero")).toBeNull();
  });
});
