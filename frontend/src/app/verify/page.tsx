import type { Metadata } from "next";
import PageShell from "@/components/PageShell";
import Tag from "@/components/Tag";
import VerifyForm from "@/components/course/VerifyForm";

export const metadata: Metadata = { title: "Verify certificate" };

export default function VerifyPage() {
  return (
    <PageShell accent="#4F46E5">
      <section className="hero">
        <div className="wrap" style={{ display: "block", maxWidth: 680 }}>
          <Tag>Certificate check</Tag>
          <h1>Verify a certificate</h1>
          <p className="lead">Enter the certificate ID printed on the certificate.</p>
          <VerifyForm />
        </div>
      </section>
    </PageShell>
  );
}
