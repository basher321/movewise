import type { Metadata } from "next";
import ContactCard from "@/components/contact/ContactCard";
import ContactForm from "@/components/contact/ContactForm";
import PageShell from "@/components/PageShell";

export const metadata: Metadata = { title: "Contact" };

export default function ContactPage() {
  return (
    <PageShell accent="#0891B2">
      <section className="hero">
        <div className="wrap" style={{ alignItems: "start" }}>
          <div>
            <h1>Let’s talk about your next step.</h1>
            <p className="lead">Book a free consultation or send us a question. An advisor replies within one working day.</p>
            <ContactCard />
          </div>
          <div className="vis">
            <h3>Consultation booking</h3>
            <ContactForm />
          </div>
        </div>
      </section>
    </PageShell>
  );
}
