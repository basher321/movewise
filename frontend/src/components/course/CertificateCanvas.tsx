"use client";

import { useEffect, useRef } from "react";
import { useSettings } from "../SettingsProvider";

export type CertificateData = {
  name: string;
  accountId: string;
  courseTitle: string;
  duration: string;
  level: string;
  issued: string; // already formatted for people
  certificateId: string;
  approved: boolean;
};

// The original logo from F01, used when Settings has no logo.
const DEFAULT_LOGO = "/logo.png";

// The font families next/font gives Sora and DM Sans.
function fonts(): { sora: string; dm: string } {
  const css = getComputedStyle(document.documentElement);
  return {
    sora: css.getPropertyValue("--font-sora").trim() || "Sora, sans-serif",
    dm: css.getPropertyValue("--font-dm-sans").trim() || "'DM Sans', sans-serif",
  };
}

// drawCert() in the reference: 1000x707, logo or company name, and a watermark until approved.
function draw(cv: HTMLCanvasElement, d: CertificateData, company: string, logo: HTMLImageElement): void {
  const x = cv.getContext("2d");
  if (!x) return;
  const W = 1000;
  const H = 707;
  const { sora, dm } = fonts();
  const g = x.createLinearGradient(0, 0, W, 0);
  x.clearRect(0, 0, W, H);
  x.fillStyle = "#fff";
  x.fillRect(0, 0, W, H);
  g.addColorStop(0, "#4F46E5");
  g.addColorStop(1, "#22D3EE");
  x.strokeStyle = g;
  x.lineWidth = 14;
  x.strokeRect(24, 24, W - 48, H - 48);
  x.lineWidth = 2;
  x.strokeStyle = "#C7CCE6";
  x.strokeRect(46, 46, W - 92, H - 92);
  x.textAlign = "center";
  x.fillStyle = "#0E1B3D";
  if (logo.complete && logo.naturalWidth) {
    const lh = 94;
    const lw = (lh * logo.naturalWidth) / logo.naturalHeight;
    x.drawImage(logo, W / 2 - lw / 2, 56, lw, lh);
  } else {
    x.font = `700 24px ${sora}`;
    x.fillText(company.toUpperCase(), W / 2, 118);
  }
  x.font = `700 50px ${sora}`;
  x.fillText("Certificate of Completion", W / 2, 196);
  x.font = `400 22px ${dm}`;
  x.fillStyle = "#55607A";
  x.fillText("This is to certify that", W / 2, 258);
  x.font = `700 ${d.name.length > 22 ? 36 : 48}px ${sora}`;
  x.fillStyle = "#4F46E5";
  x.fillText(d.name, W / 2, 336);
  x.font = `400 22px ${dm}`;
  x.fillStyle = "#55607A";
  x.fillText("has successfully completed the course", W / 2, 392);
  x.font = `700 ${d.courseTitle.length > 26 ? 30 : 36}px ${sora}`;
  x.fillStyle = "#0E1B3D";
  x.fillText(d.courseTitle, W / 2, 454);
  x.font = `400 19px ${dm}`;
  x.fillStyle = "#55607A";
  x.fillText(d.duration + " · " + d.level, W / 2, 494);
  x.strokeStyle = "#0E1B3D";
  x.lineWidth = 1.5;
  x.beginPath();
  x.moveTo(130, 598);
  x.lineTo(340, 598);
  x.moveTo(660, 598);
  x.lineTo(870, 598);
  x.stroke();
  x.font = `400 17px ${dm}`;
  x.fillText(company, 235, 624);
  x.fillText("Issued " + d.issued, 765, 624);
  x.font = `400 15px ${dm}`;
  x.fillText("Certificate ID " + d.certificateId + " · Student " + d.accountId, W / 2, 664);
  if (!d.approved) {
    x.save();
    x.translate(W / 2, H / 2);
    x.rotate(-0.5);
    x.fillStyle = "rgba(14,27,61,.11)";
    x.font = `700 64px ${sora}`;
    for (let yy = -520; yy <= 520; yy += 150) for (let xx = -760; xx <= 760; xx += 430) x.fillText("VIEW ONLY", xx, yy);
    x.restore();
  }
}

// The certificate preview with its download button, or the locked button and text.
export default function CertificateCanvas({ data }: { data: CertificateData }) {
  const { settings } = useSettings();
  const ref = useRef<HTMLCanvasElement>(null);
  const company = settings?.name ?? "";
  const logoUrl = settings?.logo_url || DEFAULT_LOGO;

  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const logo = new Image();
    const redraw = () => draw(cv, data, company, logo);
    logo.onload = redraw;
    logo.src = logoUrl;
    redraw();
    void document.fonts.ready.then(redraw);
    return () => {
      logo.onload = null;
    };
  }, [data, company, logoUrl]);

  function download() {
    ref.current?.toBlob((blob) => {
      if (!blob) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = data.certificateId + ".png";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    });
  }

  return (
    <>
      <canvas
        ref={ref}
        width={1000}
        height={707}
        style={{ marginTop: 16 }}
        aria-label={"Certificate for " + data.courseTitle}
        onContextMenu={(e) => {
          if (!data.approved) e.preventDefault();
        }}
      />
      <div className="cr">
        {data.approved ? (
          <button className="btn" type="button" onClick={download}>
            Download certificate (PNG)
          </button>
        ) : (
          <button className="btn" type="button" disabled>
            🔒 Download locked
          </button>
        )}
      </div>
      {data.approved ? null : (
        <p style={{ margin: "10px 0 0", fontSize: 14, color: "var(--muted)" }}>
          View only. Download unlocks after you complete the course and {company} approves your certificate.
        </p>
      )}
    </>
  );
}
