"use client";

import { useCallback, useEffect, useState } from "react";
import { myInvoices, type Invoice, type Module } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import type { ShowToast } from "../admin/Toast";
import InvoiceDialog from "./InvoiceDialog";
import RefundDialog from "./RefundDialog";

// "My invoices" of one module (showProfile() and section 6 in the reference): view, print and request a refund.
export default function MyInvoices({ module, toast }: { module: Module; toast: ShowToast }) {
  const [invoices, setInvoices] = useState<Invoice[] | null>(null);
  const [shown, setShown] = useState<Invoice | null>(null);
  const [refundFor, setRefundFor] = useState<string | null>(null);

  const load = useCallback(() => myInvoices(module), [module]);

  useEffect(() => {
    let live = true;
    void load()
      .then((list) => {
        if (live) setInvoices(list);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [load]);

  if (!invoices) return null;

  return (
    <>
      <h2 style={{ marginTop: 40 }}>My invoices</h2>
      {invoices.length ? (
        invoices.map((i) => (
          <div className="card" style={{ marginBottom: 14 }} key={i.no}>
            <div className="top" style={{ alignItems: "center" }}>
              <div>
                <h3 style={{ margin: 0 }}>{i.no}</h3>
                <p>
                  {i.description} · {formatDate(i.issued_at)}
                </p>
              </div>
              <b>{formatMoney(i.amount_poisha)}</b>
            </div>
            <p style={{ margin: "8px 0 12px" }}>
              Confirmation email: <b>{i.email_status === "sent" ? "sent" : i.email_status === "failed" ? "not delivered" : "on its way"}</b>
            </p>
            <button className="btn ghost sm" type="button" onClick={() => setShown(i)}>
              View / print invoice
            </button>{" "}
            {i.status === "refunded" ? (
              <span className="bd">Refunded</span>
            ) : i.refund_status === "requested" ? (
              <span className="bd warn">Refund requested</span>
            ) : i.refund_status ? null : (
              <button className="btn ghost sm" type="button" onClick={() => setRefundFor(i.no)}>
                Request refund
              </button>
            )}
          </div>
        ))
      ) : (
        <p style={{ color: "var(--muted)" }}>Invoices appear here after you pay.</p>
      )}
      <InvoiceDialog invoice={shown} open={shown !== null} onClose={() => setShown(null)} />
      {refundFor ? (
        <RefundDialog
          module={module}
          invoiceNo={refundFor}
          onClose={() => setRefundFor(null)}
          onSent={() => {
            setRefundFor(null);
            toast("Refund request sent.");
            void load().then(setInvoices);
          }}
        />
      ) : null}
    </>
  );
}
