"use client";

import { useState } from "react";
import { AI_LABELS } from "@/lib/admin/settingsForm";
import { AI_PROVIDERS, isApiError, testAiProvider, type AiProvider, type AiSettingsInput, type Settings } from "@/lib/api";
import { CheckField, TextField } from "./Field";

const SAVED_KEY = "Saved - leave empty to keep";
const MODEL_HINT: Record<AiProvider, string> = {
  claude: "e.g. claude-opus-5-5",
  openai: "Model name from your OpenAI account",
  gemini: "Model name from Google AI Studio",
  groq: "Model name from your Groq console",
};

type Props = { ai: AiSettingsInput; stored: Settings; onChange: (ai: AiSettingsInput) => void };

// B17: the AI providers in their fixed failover order (Claude, ChatGPT, Gemini, Groq): switch, model,
// API key and test.
export default function AiProviders({ ai, stored, onChange }: Props) {
  const [results, setResults] = useState<Partial<Record<AiProvider, { ok: boolean; text: string }>>>({});
  const [busy, setBusy] = useState<AiProvider | null>(null);

  const copy = (): AiSettingsInput => ({ order: [...AI_PROVIDERS], providers: { ...ai.providers } });
  const set = (p: AiProvider, change: Partial<AiSettingsInput["providers"][AiProvider]>) => {
    const next = copy();
    next.providers[p] = { ...next.providers[p], ...change };
    onChange(next);
  };

  async function test(p: AiProvider) {
    setBusy(p);
    setResults((r) => ({ ...r, [p]: undefined }));
    try {
      const r = await testAiProvider(p);
      setResults((old) => ({ ...old, [p]: r.ok ? { ok: true, text: "Works ✓" } : { ok: false, text: r.error ?? "Did not answer." } }));
    } catch (err) {
      setResults((old) => ({ ...old, [p]: { ok: false, text: isApiError(err) ? err.message : "Did not answer." } }));
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      {AI_PROVIDERS.map((p, i) => {
        const item = ai.providers[p];
        const saved = stored.ai.providers[p].key.saved;
        const result = results[p];
        return (
          <div key={p} className="xrow" style={{ display: "block", padding: "14px 0" }}>
            <div className="top" style={{ alignItems: "center", flexWrap: "wrap" }}>
              <h4 style={{ margin: 0 }}>
                {i + 1}. {AI_LABELS[p]} {saved ? <span className="bd ok">Key saved</span> : null}
              </h4>
            </div>
            <div className="fgrid" style={{ marginTop: 10, marginBottom: 0 }}>
              <CheckField label={"Use " + AI_LABELS[p]} checked={item.enabled} onChange={(v) => set(p, { enabled: v })} />
              <TextField label="Model" value={item.model} placeholder={MODEL_HINT[p]} onChange={(v) => set(p, { model: v })} />
              <TextField
                label="API key"
                type="password"
                value={item.key}
                placeholder={saved ? SAVED_KEY : undefined}
                autoComplete="new-password"
                onChange={(v) => set(p, { key: v })}
              />
            </div>
            <div className="cr" style={{ margin: "10px 0 0", alignItems: "center" }}>
              <button className="btn ghost sm" type="button" disabled={busy !== null} onClick={() => void test(p)}>
                {busy === p ? "Testing…" : "Test " + AI_LABELS[p]}
              </button>
              {result ? (
                <span style={{ fontSize: 14, fontWeight: 600, color: result.ok ? "#16A34A" : "#DC2626" }} role="status">
                  {result.text}
                </span>
              ) : null}
            </div>
          </div>
        );
      })}
      <p className="sub" style={{ margin: "8px 0 0", fontSize: 13 }}>
        Keys are stored encrypted on the server and never shown again. Save your settings first; the test uses the saved key and model. Each provider bills your own account.
      </p>
    </>
  );
}
