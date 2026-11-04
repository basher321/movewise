import type { Metadata } from "next";
import Button from "@/components/Button";
import Card from "@/components/Card";
import PageShell from "@/components/PageShell";
import AboutHero from "@/components/about/AboutHero";
import IfLicensed from "@/components/IfLicensed";
import type { Module } from "@/lib/api";

export const metadata: Metadata = { title: "About Us" };

// Each service belongs to a module and is hidden when that module is not licensed.
const SERVICES: { module: Module; card: readonly [string, string, string] }[] = [
  { module: "course", card: ["📚", "Courses", "Practical courses with a certificate."] },
  { module: "study", card: ["🎓", "Student consultancy", "From shortlist to visa."] },
  { module: "job", card: ["🛂", "Job processing", "Verified jobs and permits."] },
  { module: "visa", card: ["🌍", "Immigration processing", "Visas for every country."] },
];

const WHY = [
  ["💬", "Fixed, written fees", "No hidden charges, ever."],
  ["👤", "A named advisor", "One person who knows your file."],
  ["📈", "Live tracking", "See every update online."],
] as const;

function Cards({ items }: { items: readonly (readonly [string, string, string])[] }) {
  return items.map(([ico, title, text]) => (
    <Card key={title}>
      <div className="ico">{ico}</div>
      <h3>{title}</h3>
      <p>{text}</p>
    </Card>
  ));
}

export default function AboutPage() {
  return (
    <PageShell accent="#7C3AED">
      <div className="hero">
        <div className="wrap">
          <div>
            <AboutHero />
            <div className="acts">
              <Button href="/contact">Meet an advisor</Button>
            </div>
          </div>
          <div className="vis">
            <h3>Our mission</h3>
            <p style={{ color: "var(--muted)", margin: 0 }}>
              Give every student and worker the skills, guidance and honest information to build a life abroad, at a fixed and
              transparent cost.
            </p>
          </div>
        </div>
      </div>

      <section>
        <div className="wrap">
          <div className="head">
            <h2>Our services</h2>
          </div>
          <div className="grid">
            {SERVICES.map((s) => (
              <IfLicensed key={s.module} module={s.module}>
                <Cards items={[s.card]} />
              </IfLicensed>
            ))}
          </div>
        </div>
      </section>

      <section className="band">
        <div className="wrap">
          <div className="head">
            <h2>Why choose us</h2>
          </div>
          <div className="grid">
            <Cards items={WHY} />
          </div>
        </div>
      </section>

    </PageShell>
  );
}
