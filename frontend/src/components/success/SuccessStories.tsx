"use client";

import { useEffect, useState, type CSSProperties } from "react";
import { getSuccessStories, isApiError, NETWORK_MESSAGE, type AppModule, type SuccessStories as Data } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { accentColour, MODULE_UI } from "../auth/modules";
import LoadError from "../LoadError";
import { useSettings } from "../SettingsProvider";

// Success Stories: made automatically from cases that reached Completed (the last stage). Nobody
// types them in. The public sees a short name only, what the journey was for, the country and when.
export default function SuccessStories() {
  const { settings } = useSettings();
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [shown, setShown] = useState<AppModule | "all">("all");

  useEffect(() => {
    let live = true;
    getSuccessStories()
      .then((d) => {
        if (live) {
          setData(d);
          setError("");
        }
      })
      .catch((err: unknown) => {
        if (live) setError(isApiError(err) ? err.message : NETWORK_MESSAGE);
      });
    return () => {
      live = false;
    };
  }, [attempt]);

  if (error) return <LoadError message={error} onRetry={() => setAttempt(attempt + 1)} />;
  if (!data) return <p className="wrap">Loading…</p>;

  const total = data.summary.reduce((n, s) => n + s.completed, 0);
  const finished = data.summary.reduce((n, s) => n + s.finished, 0);
  const stories = shown === "all" ? data.stories : data.stories.filter((s) => s.module === shown);
  const tabs: [AppModule | "all", string][] = [["all", "All"], ...data.summary.map((s) => [s.module, MODULE_UI[s.module].short] as [AppModule, string])];

  return (
    <>
      <section>
        <div className="wrap">
          <div className="head">
            <h2>Our results in numbers</h2>
            <p>
              Counted automatically from every finished journey: completed cases against completed and rejected ones.
              {finished ? " " + total + " successful " + (total === 1 ? "journey" : "journeys") + " so far." : ""}
            </p>
          </div>
          <div className="grid">
            {data.summary.map((s) => (
              <div className="card" key={s.module} style={{ "--a": accentColour(s.module, settings) } as CSSProperties}>
                <div className="ico">{MODULE_UI[s.module].icon}</div>
                <p>{s.module_label}</p>
                <h3 style={{ margin: "6px 0 0" }}>{s.percent === null ? "–" : s.percent + "% success"}</h3>
                <p style={{ margin: "4px 0 0", fontSize: 13 }}>
                  {s.finished
                    ? s.completed + " of " + s.finished + " finished " + (s.finished === 1 ? "journey" : "journeys") + " succeeded"
                    : "No finished journeys yet"}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section style={{ paddingTop: 0 }}>
        <div className="wrap">
          <div className="head">
            <h2>Success stories</h2>
            <p>People who finished their journey with us, newest first.</p>
          </div>
          {tabs.length > 2 ? (
            <div
              className="seg"
              role="tablist"
              style={{ maxWidth: tabs.length * 150, gridTemplateColumns: "repeat(auto-fit,minmax(min(110px,100%),1fr))", borderRadius: 22 }}
            >
              {tabs.map(([m, label]) => (
                <button key={m} type="button" role="tab" aria-selected={shown === m} onClick={() => setShown(m)}>
                  {label}
                </button>
              ))}
            </div>
          ) : null}
          {stories.length ? (
            <div className="grid">
              {stories.map((s) => (
                <div className="card" key={s.id} style={{ "--a": accentColour(s.module, settings) } as CSSProperties}>
                  <span className="bd">
                    {MODULE_UI[s.module].icon} {s.module_label}
                  </span>
                  <h3 style={{ margin: "6px 0 4px" }}>{s.name}</h3>
                  <p style={{ margin: 0 }}>
                    <b>{s.title}</b>
                    {s.detail ? " · " + s.detail : ""}
                  </p>
                  <p style={{ margin: "4px 0 0", fontSize: 13 }}>
                    {s.country} · Completed {formatDate(s.completed_at)}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <div className="card">
              <p style={{ margin: 0 }}>Our success stories appear here as soon as a journey is completed.</p>
            </div>
          )}
        </div>
      </section>
    </>
  );
}
