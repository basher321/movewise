"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  APP_MODULES,
  listCourseGroups,
  listRemoteJobs,
  listUniversities,
  listVacancies,
  listVisaPrograms,
  myApplications,
  myEnrolments,
  type AppModule,
  type EnrolmentStatus,
  type Module,
} from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { configOf } from "./modules";
import { useSession } from "./SessionProvider";
import { isLicensed, useSettings } from "./SettingsProvider";

type Row = { key: string; done: boolean; title: string; note: string; href: string };

const ENROLMENT_NOTE: Record<EnrolmentStatus, string> = {
  awaiting_payment: "Payment waiting",
  active: "Enrolled",
  completed: "Course completed",
  cancelled: "Cancelled",
};

const MAX_ROWS = 3;
const MAX_PUBLIC = 4;

const usd = (n: number) => "$" + n.toLocaleString("en-US");

// What a visitor sees: the newest published items of one module, straight from the database.
async function publicRows(m: Module): Promise<Row[]> {
  if (m === "course") {
    const groups = await listCourseGroups();
    return groups
      .flatMap((g) => g.courses)
      .map((c) => ({
        key: "pc" + c.id,
        done: false,
        title: c.title,
        note: [c.duration, formatMoney(c.price_poisha)].filter(Boolean).join(" · "),
        href: "/courses/" + c.slug,
      }));
  }
  if (m === "study") {
    return (await listUniversities()).map((u) => ({
      key: "pu" + u.id,
      done: false,
      title: u.name,
      note: [u.city, u.country].filter(Boolean).join(", ") + " · Tuition " + usd(u.tuition_usd) + " per year",
      href: "/consultancy/" + u.slug,
    }));
  }
  if (m === "job") {
    return (await listVacancies()).map((v) => ({
      key: "pj" + v.id,
      done: false,
      title: v.title,
      note: v.employer + " · " + v.country + " · " + usd(v.salary_usd) + "/month",
      href: "/jobs/" + v.slug,
    }));
  }
  if (m === "remote") {
    return (await listRemoteJobs()).map((v) => ({
      key: "pr" + v.id,
      done: false,
      title: v.title,
      note: v.employer + " · Remote · " + usd(v.salary_usd) + "/month",
      href: "/remote-jobs/" + v.slug,
    }));
  }
  return (await listVisaPrograms()).map((v) => ({
    key: "pv" + v.id,
    done: false,
    title: v.title + " · " + v.country,
    note: [v.visa_type_label, v.processing_time].filter(Boolean).join(" · "),
    href: "/immigration/" + v.slug,
  }));
}

// The hero card, always real data from the database:
// - a signed-in applicant sees their own applications and enrolments (title);
// - everyone else sees the newest published courses, universities, jobs or visa programmes (publicTitle).
// Nothing published -> no card (or only the Settings picture when one is given).
export default function LiveProgress({
  title,
  publicTitle,
  modules,
  picture = "",
}: {
  title: string;
  publicTitle: string;
  modules: Module[];
  picture?: string;
}) {
  const { session } = useSession();
  const { licence } = useSettings();
  // Loaded rows, tagged with the accounts they were loaded for (old rows are never shown after sign-out).
  const [loaded, setLoaded] = useState<{ key: string; rows: Row[]; pct: number | null }>({ key: "", rows: [], pct: null });

  const wanted = modules.filter((m) => isLicensed(licence, m) && session?.applicants[m]);
  const key = wanted.map((m) => m + ":" + session?.applicants[m]?.id).join(",");
  const open = modules.filter((m) => isLicensed(licence, m));
  const openKey = open.join(",");
  const [catalogue, setCatalogue] = useState<{ key: string; rows: Row[] }>({ key: "", rows: [] });

  useEffect(() => {
    if (!openKey) return;
    let live = true;
    const list = openKey.split(",") as Module[];
    // One module page: its newest items. Home: the newest item of each module first, then the rest.
    void Promise.allSettled(list.map(publicRows)).then((results) => {
      if (!live) return;
      const lists = results.map((r) => (r.status === "fulfilled" ? r.value : []));
      const firsts = lists.flatMap((l) => l.slice(0, 1));
      const rest = lists.flatMap((l) => l.slice(1));
      setCatalogue({ key: openKey, rows: [...firsts, ...rest].slice(0, MAX_PUBLIC) });
    });
    return () => {
      live = false;
    };
  }, [openKey]);

  useEffect(() => {
    if (!key) return;
    let live = true;
    const list = key.split(",").map((part) => part.split(":")[0] as Module);
    const jobs = list.map(async (m): Promise<{ rows: Row[]; pct: number | null }> => {
      if (m === "course") {
        const items = await myEnrolments();
        return {
          rows: items
            .filter((e) => e.status !== "cancelled")
            .map((e) => ({
              key: "c" + e.id,
              done: e.status === "completed",
              title: e.course.title,
              note: ENROLMENT_NOTE[e.status],
              href: "/profile/course",
            })),
          pct: null,
        };
      }
      const mod = m as AppModule;
      const apps = (await myApplications(mod)).filter((a) => a.status !== "withdrawn" && a.status !== "rejected");
      const first = apps[0];
      return {
        rows: apps.map((a) => ({
          key: "a" + a.id,
          done: a.status === "completed",
          title: a.item_employer ? a.item_title + " · " + a.item_employer : a.item_title,
          note: "Stage " + (a.stage + 1) + " of " + a.stage_count + ": " + a.stage_name,
          href: configOf(mod).base + "/" + a.item_slug + "/apply",
        })),
        pct: first && first.stage_count > 1 ? Math.round((first.stage / (first.stage_count - 1)) * 100) : null,
      };
    });
    void Promise.allSettled(jobs).then((results) => {
      if (!live) return;
      const ok = results.flatMap((r) => (r.status === "fulfilled" ? [r.value] : []));
      setLoaded({
        key,
        rows: ok.flatMap((r) => r.rows).slice(0, MAX_ROWS),
        pct: ok.find((r) => r.pct !== null)?.pct ?? null,
      });
    });
    return () => {
      live = false;
    };
  }, [key]);

  const own = key && loaded.key === key ? loaded.rows : [];
  const showOwn = own.length > 0;
  const rows = showOwn ? own : openKey && catalogue.key === openKey ? catalogue.rows : [];
  const pct = showOwn ? loaded.pct : null;

  if (!rows.length) {
    return picture ? <div className="vis img" style={{ backgroundImage: `url("${picture}")` }}></div> : null;
  }

  return (
    <div className={picture ? "vis img" : "vis"} style={picture ? { backgroundImage: `url("${picture}")` } : undefined}>
      <h3>{showOwn ? title : publicTitle}</h3>
      {rows.map((r) => (
        <Link className={r.done ? "row ok" : "row"} href={r.href} key={r.key}>
          <span>{r.done ? "✓" : "•"}</span>
          <div>
            {r.title}
            <small>{r.note}</small>
          </div>
        </Link>
      ))}
      {pct !== null ? (
        <div className="bar">
          <i style={{ width: pct + "%" }}></i>
        </div>
      ) : null}
    </div>
  );
}

export const ALL_MODULES: Module[] = ["course", ...APP_MODULES];
