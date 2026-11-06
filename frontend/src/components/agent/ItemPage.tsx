"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type CSSProperties } from "react";
import {
  getMyApplication,
  isApiError,
  lastAgentInputs,
  myApplications,
  NETWORK_MESSAGE,
  stagesOf,
  startApplication,
  type AppModule,
  type MyApplication,
} from "@/lib/api";
import { formatMoney } from "@/lib/format";
import Button from "../Button";
import LoadError from "../LoadError";
import { configOf } from "../modules";
import type { ItemInfo, MatchView } from "../modules/types";
import { useSession } from "../SessionProvider";
import FeeDialog from "./FeeDialog";
import MatchChips from "./MatchChips";

// The item detail page (showItem() in the reference) for any module with applications. id is the slug.
export default function ItemPage({ module, slug: id }: { module: AppModule; slug: string }) {
  const config = configOf(module);
  const router = useRouter();
  const { session, openAuth } = useSession();
  // undefined while loading; null when the item does not exist or is hidden.
  const [item, setItem] = useState<ItemInfo | null | undefined>(undefined);
  const [match, setMatch] = useState<MatchView | null>(null);
  // The open application for this item: "self" for a Self Apply, "agent" otherwise, or none.
  const [applied, setApplied] = useState<"self" | "agent" | false>(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  // Self Apply, all on this page: the Self Apply record, the payment dialog, and the link once paid.
  const [selfApp, setSelfApp] = useState<MyApplication | null>(null);
  const [selfBusy, setSelfBusy] = useState(false);
  const [selfError, setSelfError] = useState("");
  const [paying, setPaying] = useState(false);
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
        if (!live) return;
        const open = list.find((a) => a.item_slug === id && (a.status === "active" || a.status === "on_hold"));
        setApplied(open ? (open.self_apply ? "self" : "agent") : false);
        // An open Self Apply shows here with its payment state or the link (for example after the gateway).
        if (open?.self_apply) {
          void getMyApplication(module, open.id)
            .then((found) => {
              if (live) setSelfApp(found);
            })
            .catch(() => {});
        }
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

  // Self Apply: sign in, then the Self Apply record and its payment open here. After the payment is
  // confirmed the official link shows on this page.
  async function openSelfApply() {
    setSelfBusy(true);
    setSelfError("");
    try {
      const open = (await myApplications(module)).find(
        (a) => a.item_slug === id && a.self_apply && (a.status === "active" || a.status === "on_hold"),
      );
      const found = open ? await getMyApplication(module, open.id) : await startApplication(module, id, {}, true);
      if (!found.self_apply) {
        setSelfError("You already have an agent application for this university. Open it from your profile.");
        return;
      }
      setSelfApp(found);
      setApplied("self");
      if (!found.fee_paid && found.payment?.status !== "pending_verify") setPaying(true);
    } catch (err) {
      setSelfError(isApiError(err) ? err.message : NETWORK_MESSAGE);
    } finally {
      setSelfBusy(false);
    }
  }

  function selfApply() {
    if (account) void openSelfApply();
    else openAuth({ mode: "up", module, note: config.apply.authNote, after: () => void openSelfApply() });
  }

  async function selfPaid() {
    setPaying(false);
    if (selfApp) setSelfApp(await getMyApplication(module, selfApp.id).catch(() => selfApp));
  }

  const full = { width: "100%", justifyContent: "center" };
  const twoWays = config.apply.hasLink;
  const selfFee = item.self_apply_fee_poisha ?? null;
  const stages = stagesOf(module);

  return (
    <div style={{ "--a": config.accent } as CSSProperties}>
      {paying && selfApp && account ? (
        <FeeDialog
          module={module}
          applicationId={selfApp.id}
          itemName={item.name}
          country={item.country}
          fee_poisha={selfApp.fee_poisha ?? selfFee ?? 0}
          phone={account.phone}
          feeName="Self Apply fee"
          onClose={() => setPaying(false)}
          onDone={() => void selfPaid()}
        />
      ) : null}
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
              {account && applied === "agent" ? (
                <Link className="btn" href={applyHref} style={full}>
                  Open my application →
                </Link>
              ) : twoWays ? (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <button className="btn ghost" type="button" style={full} onClick={selfApply} disabled={selfFee === null || selfBusy}>
                    Self Apply
                  </button>
                  <button className="btn" type="button" style={full} onClick={apply}>
                    Agent Apply
                  </button>
                </div>
              ) : (
                <button className="btn" type="button" style={full} onClick={apply}>
                  Apply now
                </button>
              )}
              {twoWays && !(account && applied === "agent") && !selfApp ? (
                <p style={{ margin: "10px 0 0", color: "var(--muted)", fontSize: 14 }}>
                  {selfFee === null
                    ? "Self Apply is not available for this university yet. "
                    : "Self Apply: pay " + formatMoney(selfFee) + " to get the official application link and apply on your own. "}
                  Agent Apply: our team handles your application and you follow every stage here.
                </p>
              ) : null}
              {selfError ? (
                <div className="banner no" style={{ margin: "12px 0 0" }}>
                  {selfError}
                </div>
              ) : null}
              {selfApp ? (
                <div style={{ marginTop: 14, borderTop: "1px solid var(--line)", paddingTop: 14 }}>
                  <h3 style={{ margin: "0 0 6px" }}>Self Apply</h3>
                  {selfApp.fee_paid ? (
                    <>
                      <p style={{ margin: "0 0 12px", color: "#16A34A", fontWeight: 600 }}>
                        ✓ Payment confirmed. Apply on the university website by yourself.
                      </p>
                      {selfApp.apply_link && /^https?:\/\//.test(selfApp.apply_link) ? (
                        <a className="btn" href={selfApp.apply_link} target="_blank" rel="noopener noreferrer" style={full}>
                          Open university application ↗
                        </a>
                      ) : (
                        <button className="btn" type="button" disabled style={full}>
                          {config.apply.noLink}
                        </button>
                      )}
                    </>
                  ) : selfApp.payment?.status === "pending_verify" ? (
                    <div className="banner in" style={{ margin: 0 }}>
                      Your payment ({formatMoney(selfApp.payment.amount_poisha)}) is waiting for verification by our finance team.
                      The university link appears here once it is confirmed.
                    </div>
                  ) : (
                    <>
                      <p style={{ margin: "0 0 12px", color: "var(--muted)", fontSize: 14 }}>
                        Pay the Self Apply fee to get the official university application link.
                      </p>
                      <button className="btn" type="button" style={full} onClick={() => setPaying(true)}>
                        🔒 Pay {formatMoney(selfApp.fee_poisha ?? selfFee ?? 0)}
                      </button>
                    </>
                  )}
                </div>
              ) : null}
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
            {/* Counted automatically: every journey that reaches Completed (success) or is Rejected. */}
            <div className="card">
              <p>Success rate</p>
              <h3 style={{ margin: "6px 0 0" }}>{item.success_rate ? item.success_rate.percent + "%" : "–"}</h3>
              <p style={{ margin: "4px 0 0", fontSize: 13 }}>
                {item.success_rate
                  ? item.success_rate.completed + " of " + item.success_rate.finished + " finished " + (item.success_rate.finished === 1 ? "journey" : "journeys") + " succeeded"
                  : "No finished journeys yet"}
              </p>
            </div>
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
