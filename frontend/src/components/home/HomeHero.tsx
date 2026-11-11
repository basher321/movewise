"use client";

import Button from "@/components/Button";
import IfLicensed from "@/components/IfLicensed";
import LiveProgress, { ALL_MODULES } from "@/components/LiveProgress";
import { useSettings } from "@/components/SettingsProvider";
import Tag from "@/components/Tag";

// Home hero from Settings (applyBrand() in the reference). The Settings picture, or the signed-in applicant's real progress.
export default function HomeHero() {
  const { settings, licence } = useSettings();
  const picture = settings?.hero_url ?? "";
  // An empty setting falls back to the reference default text (SET0), plus Visas when Immigration (B19) and
  // Remote jobs when Remote Jobs is licensed.
  const fallbackTagline =
    "Courses · Study abroad · Jobs abroad" + (licence?.modules.visa ? " · Visas" : "") + (licence?.modules.remote ? " · Remote jobs" : "");
  const tagline = settings ? settings.tagline || fallbackTagline : "";
  const title = settings ? settings.hero_title || "Build skills here. Build your future anywhere." : "";
  const text = settings
    ? settings.hero_text ||
      "Future-ready courses, study-abroad guidance and verified overseas jobs, all in one place and one account."
    : "";
  return (
    <div className="hero">
      <div className="wrap">
        <div>
          <Tag>{tagline}</Tag>
          <h1>{title}</h1>
          <p className="lead">{text}</p>
          <div className="acts">
            <IfLicensed module="study">
              <Button href="/consultancy">Start your journey</Button>
            </IfLicensed>
            <IfLicensed module="course">
              <Button variant="ghost" href="/courses">
                Browse courses
              </Button>
            </IfLicensed>
            <Button variant="ghost" href="/contact">
              Book consultation
            </Button>
          </div>
          <div className="stats">
            {(settings?.stats ?? [])
              .filter((s) => s.number)
              .map((s, i) => (
                <div key={i}>
                  <b>{s.number}</b>
                  {s.label}
                </div>
              ))}
          </div>
        </div>
        <LiveProgress title="Your journey, tracked live" publicTitle="Open now" modules={ALL_MODULES} picture={picture} />
      </div>
    </div>
  );
}
