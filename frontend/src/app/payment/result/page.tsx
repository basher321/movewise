import { Suspense } from "react";
import type { Metadata } from "next";
import PageShell from "@/components/PageShell";
import Tag from "@/components/Tag";
import PaymentResult from "@/components/payment/PaymentResult";

export const metadata: Metadata = { title: "Payment" };

// Where SSLCommerz and bKash send the payer back (/payment/result?id=).
export default function PaymentResultPage() {
  return (
    <PageShell accent="brand">
      <section className="hero">
        <div className="wrap" style={{ display: "block", maxWidth: 680 }}>
          <Tag>Payment</Tag>
          <h1>Your payment</h1>
          <Suspense fallback={<p style={{ color: "var(--muted)" }}>Loading…</p>}>
            <PaymentResult />
          </Suspense>
        </div>
      </section>
    </PageShell>
  );
}
