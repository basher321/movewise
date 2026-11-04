"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { COUNTRY_FLAGS, myApplications, type ApplicantAccount, type AppModule, type AppStatus, type MyApplicationSummary } from "@/lib/api";
import type { ShowToast } from "../admin/Toast";
import { configOf } from "../modules";
import MyInvoices from "../payment/MyInvoices";

const STATUS: Record<AppStatus, [string, string]> = {
  active: ["Active", "ok"],
  on_hold: ["On hold", "warn"],
  rejected: ["Rejected", "no"],
  withdrawn: ["Withdrawn", ""],
  completed: ["Completed", "info"],
};

// The profile tab of a module with applications (appsHtml() in the reference): "My applications", then "My invoices".
export default function ApplicationsProfile({ module, account, toast }: { module: AppModule; account: ApplicantAccount; toast: ShowToast }) {
  const config = configOf(module);
  const [apps, setApps] = useState<MyApplicationSummary[] | null>(null);

  useEffect(() => {
    let live = true;
    void myApplications(module)
      .then((list) => {
        if (live) setApps(list);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [module, account.id]);

  if (!apps) return null;

  return (
    <div>
      <h2>My applications</h2>
      {apps.length ? (
        apps.map((a) => {
          const pct = Math.round((a.stage / (a.stage_count - 1)) * 100);
          const name = a.item_employer ? a.item_title + " · " + a.item_employer : a.item_title;
          return (
            <Link className="card" href={config.base + "/" + a.item_slug + "/apply"} style={{ marginBottom: 18, display: "block" }} key={a.id}>
              <div className="top" style={{ alignItems: "center" }}>
                <h3 style={{ margin: 0 }}>{name}</h3>
                <span className={"bd " + STATUS[a.status][1]}>{STATUS[a.status][0]}</span>
              </div>
              <p>
                {a.ref} · {COUNTRY_FLAGS[a.item_country] ?? ""} {a.item_country} · Stage {a.stage + 1} of {a.stage_count}: {a.stage_name}
                {a.fee_paid ? "" : " · fee not paid yet"}
              </p>
              <div className="bar">
                <i style={{ width: pct + "%" }}></i>
              </div>
            </Link>
          );
        })
      ) : (
        <p style={{ color: "var(--muted)", margin: "0 0 24px" }}>
          {config.apply.noApplications}{" "}
          <Link href={config.base} style={{ color: "var(--a)", fontWeight: 600 }}>
            {config.apply.findLabel}
          </Link>
          .
        </p>
      )}
      <MyInvoices module={module} toast={toast} />
    </div>
  );
}
