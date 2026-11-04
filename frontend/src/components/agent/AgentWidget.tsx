"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import {
  askAgent,
  COUNTRY_FLAGS,
  getCatalogOptions,
  isApiError,
  lastAgentInputs,
  rememberAgentInputs,
  type AgentInputs,
  type AppModule,
  type CatalogOptions,
} from "@/lib/api";
import { configOf } from "../modules";
import type { AgentConfig, AgentField, MatchView } from "../modules/types";
import MatchChips from "./MatchChips";

type AgentWidgetProps = {
  module: AppModule;
  config: AgentConfig;
  onSelect: (itemId: string) => void;
};

type Bubble = { id: number; who: "bot" | "me"; text: string };

// The text a remembered answer shows in its box.
function shown(f: AgentField, x: unknown): string {
  if (f.asBoolean && typeof x === "boolean") return x ? f.asBoolean : (f.options ?? []).find((o) => o !== f.asBoolean) ?? "";
  return x === null || x === undefined ? "" : String(x);
}

// The agent section (mountAgent() in the reference): the input form, the chat card and the results.
export default function AgentWidget({ module, config, onSelect }: AgentWidgetProps) {
  const [options, setOptions] = useState<CatalogOptions | null>(null);
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(config.fields.map((f) => [f.key, f.options ? String(f.options[0]) : ""])),
  );
  const choices = (f: AgentField): readonly string[] | undefined => (f.optionsFrom ? (options?.[f.optionsFrom] ?? []) : f.options);
  const empty = options !== null && config.fields.some((f) => f.optionsFrom && !options[f.optionsFrom].length);
  const [inputs, setInputs] = useState<AgentInputs | null>(null);
  const [results, setResults] = useState<MatchView[] | null>(null);
  const [error, setError] = useState("");
  const [question, setQuestion] = useState("");
  const [log, setLog] = useState<Bubble[]>([{ id: 0, who: "bot", text: "Hi! Fill in your details and I will match you. You can also ask me anything." }]);
  const formRef = useRef<HTMLFormElement>(null);
  const resRef = useRef<HTMLDivElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);

  // The choices the agency offers now. Selects start on their first choice.
  useEffect(() => {
    let live = true;
    void getCatalogOptions()
      .then((o) => {
        if (!live) return;
        setOptions(o);
        setValues((v) => {
          const next = { ...v };
          for (const f of config.fields) {
            const list = f.optionsFrom ? o[f.optionsFrom] : null;
            if (list && !list.includes(next[f.key])) next[f.key] = list[0] ?? "";
          }
          return next;
        });
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [config]);

  // The last inputs are shown again on return, with their results.
  useEffect(() => {
    let live = true;
    void lastAgentInputs(module).then(async (last) => {
      if (!live || !last) return;
      const byKey = Object.fromEntries(config.fields.map((f) => [f.key, f]));
      setValues((v) => ({
        ...v,
        ...Object.fromEntries(Object.entries(last).filter(([k]) => byKey[k]).map(([k, x]) => [k, shown(byKey[k], x)])),
      }));
      setInputs(last);
      try {
        const found = await configOf(module).match(last);
        if (live) setResults(found);
      } catch {
        // Remembered inputs that no longer match the form are ignored.
      }
    });
    return () => {
      live = false;
    };
  }, [module, config]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [log]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const next: AgentInputs = {};
    for (const f of config.fields) {
      const raw = values[f.key] ?? "";
      if (f.asBoolean) {
        next[f.key] = raw === f.asBoolean;
        continue;
      }
      if (choices(f)) {
        if (!raw) {
          setError("Please choose: " + f.label + ".");
          return;
        }
        next[f.key] = raw;
        continue;
      }
      if (raw.trim() === "") {
        if (f.required) {
          setError("Please fill in: " + f.label + ".");
          formRef.current?.querySelector<HTMLInputElement>(`[name="${f.key}"]`)?.focus();
          return;
        }
        next[f.key] = f.empty ?? "";
        continue;
      }
      next[f.key] = parseFloat(raw);
    }
    try {
      const found = await configOf(module).match(next);
      setError("");
      setInputs(next);
      setResults(found);
      void rememberAgentInputs(module, next);
      requestAnimationFrame(() => resRef.current?.scrollIntoView({ behavior: "smooth" }));
    } catch (err) {
      setError(isApiError(err) ? err.message : "Something went wrong. Please try again.");
    }
  }

  async function send() {
    const q = question.trim();
    if (!q) return;
    setQuestion("");
    const me = nextId.current++;
    const bot = nextId.current++;
    setLog((l) => [...l, { id: me, who: "me", text: q }, { id: bot, who: "bot", text: "Thinking…" }]);
    let reply: string;
    try {
      reply = await askAgent(module, q, inputs);
    } catch (err) {
      reply = isApiError(err) ? err.message : "Something went wrong. Please try again.";
    }
    setLog((l) => l.map((b) => (b.id === bot ? { ...b, text: reply } : b)));
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      void send();
    }
  }

  return (
    <>
      <div className="head">
        <span className="tag">AI agent</span>
        <h2>{config.title}</h2>
        <p>{config.subtitle}</p>
      </div>
      <div className="two" style={{ alignItems: "start" }}>
        <form ref={formRef} className="card" noValidate onSubmit={submit}>
          <div className="fgrid">
            {config.fields.map((f) => (
              <label className="fl" key={f.key}>
                <span>{f.label}</span>
                {choices(f) ? (
                  <select name={f.key} value={values[f.key]} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}>
                    {(choices(f) ?? []).map((o) => (
                      <option key={o}>{o}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    name={f.key}
                    type="number"
                    min={f.min}
                    max={f.max}
                    step={f.step}
                    placeholder={f.placeholder}
                    value={values[f.key]}
                    onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                  />
                )}
              </label>
            ))}
          </div>
          {empty ? (
            <p className="sub" style={{ margin: "12px 0" }}>
              {config.nothingOpen}{" "}
              <Link href="/contact" style={{ color: "var(--a)", fontWeight: 600 }}>
                Contact us
              </Link>
              .
            </p>
          ) : null}
          <p className="err" role="alert">
            {error}
          </p>
          <button className="btn" type="submit" disabled={empty}>
            {config.button}
          </button>
        </form>
        <div className="card chat">
          <h3>
            {config.icon} {config.name}
          </h3>
          <div className="log" aria-live="polite" ref={logRef}>
            {log.map((b) => (
              <div className={"b " + b.who} key={b.id}>
                {b.text}
              </div>
            ))}
          </div>
          <div className="cr">
            <input value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={onKey} placeholder={config.chatPlaceholder} aria-label="Ask the agent" />
            <button className="btn sm" type="button" onClick={() => void send()}>
              Ask
            </button>
          </div>
        </div>
      </div>
      <div className="res" ref={resRef}>
        {results === null ? null : (
          <>
            <h3 className="rh">{results.length ? config.resultsHeading(results.length) : "No match yet"}</h3>
            {results.length ? (
              <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(300px,1fr))" }}>
                {results.map((m) => (
                  <div className="card" key={m.id}>
                    <div className="top">
                      <div>
                        <h3 style={{ margin: 0 }}>{m.name}</h3>
                        <p>
                          {COUNTRY_FLAGS[m.country] ?? ""} {m.country} · {m.place}
                        </p>
                      </div>
                      <span className="pct">{m.percent}%</span>
                    </div>
                    <MatchChips checks={m.checks} />
                    <button className="btn sm" type="button" onClick={() => onSelect(m.id)}>
                      Select &amp; view details
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ color: "var(--muted)" }}>
                {config.noMatch}{" "}
                <Link href="/contact" style={{ color: "var(--a)", fontWeight: 600 }}>
                  book a free consultation
                </Link>
                .
              </p>
            )}
          </>
        )}
      </div>
    </>
  );
}
