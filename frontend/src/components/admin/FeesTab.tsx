"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  COUNTRY_FLAGS,
  getFees,
  listAdminUniversities,
  listAdminVacancies,
  listAdminVisaPrograms,
  resetFees,
  saveFees,
  type AppModule,
  type FeeChanges,
  type LicenceView,
  type University,
  type Vacancy,
  type VisaProgram,
} from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { errorText } from "../auth/messages";
import { handleFailure } from "./failure";
import type { ShowToast } from "./Toast";

type Row = { module: AppModule; id: string; country: string; name: string; sub: string; fee: number };

const keyOf = (r: { module: AppModule; id: string }) => r.module + ":" + r.id;

type Props = { licence: LicenceView; toast: ShowToast; onSignedOut: () => void };

// The Fees tab (showFees() in the reference): one fee box per job, university and visa programme.
export default function FeesTab({ licence, toast, onSignedOut }: Props) {
  const [defaults, setDefaults] = useState<{ study: number; job: number; visa: number } | null>(null);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const form = useRef<HTMLFormElement>(null);

  const load = useCallback(async () => {
    try {
      // Admin lists: hidden, closed and unverified items too, each with its effective fee.
      const [fees, jobs, unis, visas] = await Promise.all([
        getFees(),
        licence.modules.job ? listAdminVacancies() : Promise.resolve([] as Vacancy[]),
        licence.modules.study ? listAdminUniversities() : Promise.resolve([] as University[]),
        licence.modules.visa ? listAdminVisaPrograms() : Promise.resolve([] as VisaProgram[]),
      ]);
      setDefaults(fees.defaults);
      const next: Row[] = [
        ...jobs.map((j) => ({ module: "job" as const, id: j.id, country: j.country, name: j.title, sub: j.employer + " · " + j.occupation, fee: j.fee_poisha })),
        ...unis.map((u) => ({ module: "study" as const, id: u.id, country: u.country, name: u.name, sub: u.city || u.levels.join(", "), fee: u.fee_poisha })),
        ...visas.map((v) => ({ module: "visa" as const, id: v.id, country: v.country, name: v.title, sub: v.visa_type_label, fee: v.fee_poisha })),
      ];
      setRows(next);
      setValues(Object.fromEntries(next.map((r) => [keyOf(r), String(r.fee / 100)])));
    } catch (err) {
      handleFailure(err, toast, onSignedOut);
    }
  }, [licence, toast, onSignedOut]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  if (!rows || !defaults) return null;

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy || !rows || !defaults) return;
    // Whole taka above 0, converted with whole numbers (never a float for money).
    const bad = rows.find((r) => !/^\d+$/.test(values[keyOf(r)]?.trim() ?? "") || Number(values[keyOf(r)]) <= 0);
    if (bad) {
      setMessage({ text: "Every fee must be above 0.", ok: false });
      form.current?.querySelector<HTMLInputElement>('input[name="' + keyOf(bad) + '"]')?.focus();
      return;
    }
    const changes: FeeChanges = {};
    for (const r of rows) {
      const poisha = Number(values[keyOf(r)].trim()) * 100;
      (changes[r.module] ??= {})[r.id] = poisha === defaults[r.module] ? null : poisha;
    }
    setBusy(true);
    try {
      await saveFees(changes);
      setMessage({ text: "Fees saved.", ok: true });
      await load();
    } catch (err) {
      setMessage({ text: errorText(err), ok: false });
      handleFailure(err, () => undefined, onSignedOut);
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    if (!confirm("Reset every fee to its default?")) return;
    try {
      await resetFees("all");
      setMessage(null);
      await load();
    } catch (err) {
      handleFailure(err, toast, onSignedOut);
    }
  }

  const card = (module: AppModule, title: string) => (
    <div className="card" style={{ marginBottom: 24 }}>
      <h3 style={{ marginBottom: 12 }}>{title}</h3>
      <div className="lg h">
        <span>Country</span>
        <span>Name</span>
        <span>Default</span>
        <span style={{ textAlign: "right" }}>Fee (৳)</span>
      </div>
      {rows.some((r) => r.module === module) ? null : (
        <p style={{ color: "var(--muted)", margin: "8px 0 0" }}>Nothing here yet. Add items in the Catalog tab.</p>
      )}
      {rows
        .filter((r) => r.module === module)
        .map((r) => (
          <div className="lg" key={keyOf(r)}>
            <span>
              {COUNTRY_FLAGS[r.country] ?? "🌐"} {r.country}
            </span>
            <div>
              <b>{r.name}</b>
              <small>{r.sub}</small>
            </div>
            <span>{formatMoney(defaults[module])}</span>
            <div style={{ textAlign: "right" }}>
              <input
                type="number"
                min="1"
                step="1"
                name={keyOf(r)}
                value={values[keyOf(r)] ?? ""}
                onChange={(e) => setValues((old) => ({ ...old, [keyOf(r)]: e.target.value }))}
                style={{ maxWidth: 130, textAlign: "right" }}
                aria-label={"Fee for " + r.name}
              />
            </div>
          </div>
        ))}
    </div>
  );

  return (
    <>
      <p style={{ marginBottom: 18, maxWidth: 640 }}>
        Set the application fee for each job, university and visa programme. Applicants see this exact amount before paying. Fees that were already paid or
        started do not change. The default fees are set in Settings.
      </p>
      <form ref={form} noValidate onSubmit={(e) => void save(e)}>
        {licence.modules.job ? card("job", "Jobs") : null}
        {licence.modules.study ? card("study", "Universities") : null}
        {licence.modules.visa ? card("visa", "Visa programmes") : null}
        <p className="err" role="alert" style={message?.ok ? { color: "#16A34A" } : undefined}>
          {message?.text}
        </p>
        <div className="cr" style={{ marginTop: 0 }}>
          <button className="btn" type="submit" disabled={busy}>
            Save fees
          </button>
          <button className="btn ghost" type="button" onClick={() => void reset()}>
            Reset all to default
          </button>
        </div>
      </form>
    </>
  );
}
