"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type CSSProperties } from "react";
import { isApiError, lastAgentInputs, myApplications, NETWORK_MESSAGE, stagesOf, type AppModule } from "@/lib/api";
import Button from "../Button";
import LoadError from "../LoadError";
import { configOf } from "../modules";
import type { ItemInfo, MatchView } from "../modules/types";
import { useSession } from "../SessionProvider";
import MatchChips from "./MatchChips";

// The item detail page (showItem() in the reference) for any module with applications. id is the slug.
export default function ItemPage({ module, slug: id }: { module: AppModule; slug: string }) {
  const config = configOf(module);
  const router = useRouter();
  const { session, openAuth } = useSession();
  // undefined while loading; null when the item does not exist or is hidden.
  const [item, setItem] = useState<ItemInfo | null | undefined>(undefined);
  const [match, setMatch] = useState<MatchView | null>(null);
  const [applied, setApplied] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const account = session?.applicants[module];
  const applyHref = config.base + "/" + id + "/apply";

  useEffect(() => {
    let live = true;
    configOf(module)
      .loadItem(id)
      .then((info) => {
        if (live) {
          setItem(info);
          setError("");
        }
      })
      .catch((err: unknown) => {
        if (!live) return;
        if (isApiError(err) && err.code === "NOT_FOUND") setItem(null);
        else if (!(isApiError(err) && err.code === "MODULE_NOT_LICENSED")) setError(isApiError(err) ? err.message : NETWORK_MESSAGE);
      });
    void lastAgentInputs(module).then(async (inputs) => {
      if (!inputs) return;
      try {
        const found = (await configOf(module).match(inputs)).find((m) => m.id === id) ?? null;
        if (live) setMatch(found);
      } catch {
        // No match chips for inputs that no longer fit the form.
      }
    });
    return () => {
      live = false;
    };
  }, [module, id, attempt]);

  useEffect(() => {
    let live = true;
    if (!account) return;
    void myApplications(module)
      .then((list) => {
        if (live) setApplied(list.some((a) => a.item_slug === id && (a.status === "active" || a.status === "on_hold")));
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [account, module, id]);

  if (error) return <LoadError message={error} onRetry={() => setAttempt(attempt + 1)} />;
  if (item === undefined) return null;
  if (item === null) {
    return (
      <section>
        <div className="wrap">
          <div className="card">
            <h3>Not found</h3>
            <div className="cr">
              <Button variant="ghost" size="sm" href={config.base}>
                {config.item.notFoundLink}
              </Button>
            </div>
          </div>
        </div>
      </section>
    );
  }

  function apply() {
    if (account) router.push(applyHref);
    else openAuth({ mode: "up", module, note: config.apply.authNote, after: () => router.push(applyHref) });
  }

  const full = { width: "100%", justifyContent: "center" };
  const stages = stagesOf(module);

  return (
    <div style={{ "--a": config.accent } as CSSProperties}>
      <div className="hero">
        <div className="wrap">
          <div>
            <Link className="crumb" href={config.base + "#" + config.item.agentAnchor}>
              {config.item.crumb}
            </Link>
            <br />
            <span className="tag">{item.tag}</span>
            <h1>{item.name}</h1>
            <p className="lead">{item.lead}</p>
          </div>
          <div className="vis">
            {match ? (
              <>
                <h3>Your match: {match.percent}%</h3>
                <MatchChips checks={match.checks} />
              </>
            ) : null}
            <div style={{ marginTop: match ? 18 : 0 }}>
              {account && applied ? (
                <Link className="btn" href={applyHref} style={full}>
                  Open my application →
                </Link>
              ) : (
                <button className="btn" type="button" style={full} onClick={apply}>
                  Apply now
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
      <section>
        <div className="wrap">
          <div className="head">
            <h2>Key facts</h2>
          </div>
          <div className="grid">
            {item.facts.map(([label, value]) => (
              <div className="card" key={label}>
                <p>{label}</p>
                <h3 style={{ margin: "6px 0 0" }}>{value}</h3>
              </div>
            ))}
          </div>
        </div>
      </section>
      <section style={{ paddingTop: 0 }}>
        <div className="wrap">
          <h2>All conditions</h2>
          <ul className="list">
            {item.conditions.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      </section>
      <section className="band">
        <div className="wrap">
          <div className="head">
            <h2>How your application is processed</h2>
            <p>Follow every stage from application to departure, in your profile.</p>
          </div>
          <div className="road" style={{ "--n": config.item.roadColumns, rowGap: 28 } as CSSProperties}>
            {stages.map((s, i) => (
              <div key={s}>
                <h3>
                  {i + 1}. {s}
                </h3>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
