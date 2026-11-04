"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { myEnrolments, type ApplicantAccount, type Enrolment } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import type { ShowToast } from "../admin/Toast";
import CertificateCanvas from "../course/CertificateCanvas";
import { METHOD_NAMES } from "../payment/methods";
import MyInvoices from "../payment/MyInvoices";

// The Courses tab of the profile (showProfile("course") and section 6 in the reference):
// payments waiting for verification, "My courses & certificates" and "My invoices".
export default function CourseProfile({ account, toast }: { account: ApplicantAccount; toast: ShowToast }) {
  const [data, setData] = useState<Enrolment[] | null>(null);

  const load = useCallback(() => myEnrolments(), []);

  useEffect(() => {
    let live = true;
    void load()
      .then((d) => {
        if (live) setData(d);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [load, account.id]);

  if (!data) return null;

  return (
    <div>
      {data
        .filter((e) => e.status === "awaiting_payment" && e.payment_status === "pending_verify")
        .map((e) => (
          <div className="banner in" key={e.id}>
            Your payment for {e.course.title} ({formatMoney(e.price_poisha)}, order {e.order_no}) is waiting for verification.
          </div>
        ))}
      <h2>My courses &amp; certificates</h2>
      {data.some((e) => e.status === "active" || e.status === "completed" || e.status === "cancelled") ? (
        data
          .filter((e) => e.status !== "awaiting_payment")
          .map((e) => {
          const title = e.course.title;
          if (e.status === "cancelled") {
            return (
              <div className="card" key={e.id}>
                <h3>{title}</h3>
                <p style={{ margin: 0 }}>
                  Order {e.order_no} · refunded and cancelled
                </p>
              </div>
            );
          }
          return (
            <div className={"card cert" + (e.certificate_approved ? "" : " lock")} key={e.id}>
              <h3>{title}</h3>
              <p>
                Order {e.order_no} · {formatMoney(e.price_poisha)}
                {e.method ? " via " + METHOD_NAMES[e.method] : ""} · {formatDate(e.enrolled_at)}
              </p>
              <CertificateCanvas
                data={{
                  name: account.name,
                  accountId: account.id,
                  courseTitle: title,
                  duration: e.course.duration,
                  level: e.course.level,
                  issued: formatDate(e.certificate_approved_at ?? e.enrolled_at, "long"),
                  certificateId: e.certificate_id ?? "",
                  approved: e.certificate_approved,
                }}
              />
            </div>
          );
        })
      ) : (
        <p style={{ color: "var(--muted)" }}>
          No courses yet. <Link href="/courses">See all courses</Link>
        </p>
      )}
      <MyInvoices module="course" toast={toast} />
    </div>
  );
}
