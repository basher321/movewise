"use client";

import Button from "@/components/Button";
import IfLicensed from "@/components/IfLicensed";
import { useSettings } from "@/components/SettingsProvider";
import Tag from "@/components/Tag";

// Home hero from Settings (applyBrand() in the reference). With no home picture, the tracking card is shown.
export default function HomeHero() {
  const { settings, licence } = useSettings();
  const picture = settings?.hero_url ?? "";
  // An empty setting falls back to the reference default text (SET0), plus Visas when Immigration (B19) is licensed.
  const fallbackTagline = "Courses · Study abroad · Jobs abroad" + (licence?.modules.visa ? " · Visas" : "");
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
        <div className={picture ? "vis img" : "vis"} style={picture ? { backgroundImage: `url("${picture}")` } : undefined}>
          <h3>Your journey, tracked live</h3>
          <div className="row ok">
            <span>✓</span>
            <div>
              IELTS Speaking<small>Course completed</small>
            </div>
          </div>
          <div className="row ok">
            <span>✓</span>
            <div>
              Documents verified<small>12 of 12 uploaded</small>
            </div>
          </div>
          <div className="row">
            <span>•</span>
            <div>
              University review<small>Decision in about 9 days</small>
            </div>
          </div>
          <div className="bar">
            <i style={{ width: "62%" }}></i>
          </div>
        </div>
      </div>
    </div>
  );
}
