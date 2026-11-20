"use client";

// AI CV Agent (B28): /cv-agent - the dashboard (saved CVs, "Create new CV") and the wizard.
// Part of Core: any signed-in applicant of any licensed service. The CV belongs to the account of
// the service the person came from (?from=job) or is signed in to.

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  createCv,
  deleteCv,
  duplicateCv,
  listCvs,
  MODULES,
  type CvProject,
  type CvType,
  type Module,
} from "@/lib/api";
import { cvTitle } from "@/lib/cv/wizard";
import { formatDate } from "@/lib/format";
import { MODULE_UI } from "../auth/modules";
import { errorText } from "../auth/messages";
import PageShell from "../PageShell";
import { useSession } from "../SessionProvider";
import { useSettings } from "../SettingsProvider";
import { CV_FLAGS, CV_TEXT, CV_TYPE_CARDS } from "./strings";
import Wizard from "./Wizard";

function isModule(value: string | null): value is Module {
  return !!value && (MODULES as readonly string[]).includes(value);
}

export default function CvAgentView() {
  const router = useRouter();
  const params = useSearchParams();
  const { settings, licence } = useSettings();
  const { session, openAuth } = useSession();
  const [items, setItems] = useState<CvProject[] | null>(null);
  const [error, setError] = useState("");
  const [cover, setCover] = useState(false);
  const [sure, setSure] = useState<string | null>(null);

  const licensed = licence ? MODULES.filter((m) => licence.modules[m]) : [];
  const from = params.get("from");
  const signedIn = session ? licensed.filter((m) => session.applicants[m]) : [];
  const service: Module | null = isModule(from) && licensed.includes(from) ? from : (signedIn[0] ?? licensed[0] ?? null);
  const account = service && session ? session.applicants[service] : undefined;
  const openId = params.get("cv");

  const accountId = account?.id ?? null;
  const [reloads, setReloads] = useState(0);

  function link(cv: string | null) {
    const q = new URLSearchParams();
    if (service) q.set("from", service);
    if (cv) q.set("cv", cv);
    router.push("/cv-agent?" + q.toString());
  }

  const load = () => setReloads((n) => n + 1);

  useEffect(() => {
    if (!service || !accountId) return;
    let live = true;
    void listCvs(service)
      .then((r) => live && setItems(r.items))
      .catch((err) => live && setError(errorText(err)));
    return () => {
      live = false;
    };
  }, [service, accountId, openId, reloads]);

  if (!licence || !session || !service) return null;
  const company = settings?.name ?? "";

  async function start(type: CvType | null) {
    if (!service) return;
    try {
      const p = await createCv(service, type, cover);
      link(p.id);
    } catch (err) {
      setError(errorText(err));
    }
  }

  const header = (
    <div className="head" style={{ textAlign: "left", maxWidth: "none" }}>
      <span className="tag">🤖 {CV_TEXT.product}</span>
      <h1 style={{ fontSize: "clamp(28px,5vw,44px)" }}>
        {company ? company + " — " : ""}
        {CV_TEXT.productLong}
      </h1>
      <p>{CV_TEXT.tagline}</p>
    </div>
  );

  return (
    <PageShell accent="#4F46E5">
      <section>
        <div className="wrap">
          {!account ? (
            <>
              {header}
              <div className="card" style={{ maxWidth: 640 }}>
                <h3>{CV_TEXT.signInTitle}</h3>
                <p>{CV_TEXT.signInText}</p>
                {licensed.length > 1 ? (
                  <div className="tabs2">
                    {licensed.map((m) => (
                      <button key={m} type="button" aria-pressed={m === service} onClick={() => router.push("/cv-agent?from=" + m)}>
                        {MODULE_UI[m].icon} {MODULE_UI[m].name}
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="acts">
                  <button className="btn" type="button" onClick={() => openAuth({ mode: "in", module: service })}>
                    Sign in to {MODULE_UI[service].name}
                  </button>
                  <button className="btn ghost" type="button" onClick={() => openAuth({ mode: "up", module: service })}>
                    Create an account
                  </button>
                </div>
              </div>
            </>
          ) : openId ? (
            <Wizard
              key={openId}
              module={service}
              id={openId}
              onExit={() => {
                link(null);
              }}
            />
          ) : (
            <>
              {header}
              <p className="sub" style={{ marginTop: -8 }}>
                {CV_TEXT.how} Signed in as {account.name} ({MODULE_UI[service].icon} {MODULE_UI[service].name}).
              </p>
              <div className="top" style={{ alignItems: "center", flexWrap: "wrap", gap: 10, margin: "18px 0 12px" }}>
                <h2 style={{ margin: 0 }}>{CV_TEXT.create}</h2>
                <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input type="checkbox" checked={cover} onChange={(e) => setCover(e.target.checked)} />
                  {CV_TEXT.coverToggle}
                </label>
              </div>
              <div className="cvcards">
                {CV_TYPE_CARDS.map((c) => (
                  <button key={c.type} type="button" className="cvcard" onClick={() => void start(c.type)}>
                    <i>{c.icon}</i>
                    <b>{c.title}</b>
                    <small>{c.subtitle}</small>
                  </button>
                ))}
              </div>
              <p className="err" role="alert">
                {error}
              </p>

              <h2 style={{ margin: "28px 0 12px" }}>{CV_TEXT.myCvs}</h2>
              {items === null ? null : items.length ? (
                <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(min(300px,100%),1fr))" }}>
                  {items.map((p) => {
                    const type = CV_TYPE_CARDS.find((c) => c.type === p.cv_type);
                    return (
                      <div className="card" key={p.id}>
                        <div className="top" style={{ alignItems: "center" }}>
                          <h3 style={{ margin: 0, overflowWrap: "anywhere" }}>
                            {type?.icon ?? "📝"} {cvTitle(p, type?.title)}
                          </h3>
                          <span className={"bd " + (p.status === "approved" ? "ok" : "warn")}>{p.status === "approved" ? "Approved" : "Draft"}</span>
                        </div>
                        <p style={{ margin: "8px 0" }}>
                          {p.country ? (CV_FLAGS[p.country] ?? "🌍") + " " + p.country : "Country not chosen"} · Last edited {formatDate(p.updated_at)}
                        </p>
                        <div className="cr" style={{ flexWrap: "wrap" }}>
                          <button className="btn sm" type="button" onClick={() => link(p.id)}>
                            Open
                          </button>
                          <button
                            className="btn ghost sm"
                            type="button"
                            onClick={() =>
                              void duplicateCv(service, p.id)
                                .then(load)
                                .catch((err) => setError(errorText(err)))
                            }
                          >
                            Duplicate
                          </button>
                          {sure === p.id ? (
                            <>
                              <button
                                className="btn sm"
                                type="button"
                                style={{ background: "#DC2626" }}
                                onClick={() =>
                                  void deleteCv(service, p.id)
                                    .then(() => {
                                      setSure(null);
                                      load();
                                    })
                                    .catch((err) => setError(errorText(err)))
                                }
                              >
                                Yes, delete
                              </button>
                              <button className="btn ghost sm" type="button" onClick={() => setSure(null)}>
                                Keep
                              </button>
                            </>
                          ) : (
                            <button className="btn ghost sm" type="button" onClick={() => setSure(p.id)}>
                              Delete
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="sub">{CV_TEXT.noCvs}</p>
              )}
              <div className="ch" style={{ marginTop: 26 }}>
                {CV_TEXT.badges.map((b) => (
                  <span className="y" key={b}>
                    ✓ {b}
                  </span>
                ))}
              </div>
              <p className="sub" style={{ fontSize: 13 }}>
                {CV_TEXT.honest}
              </p>
            </>
          )}
        </div>
      </section>
    </PageShell>
  );
}
