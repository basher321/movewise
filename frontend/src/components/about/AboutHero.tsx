"use client";

import { useSettings } from "@/components/SettingsProvider";

// About headline and text from Settings (applyBrand() in the reference).
// An empty setting falls back to the reference default text (SET0), with the company name from Settings.
export default function AboutHero() {
  const { settings } = useSettings();
  const title = settings ? settings.about_title || `We started ${settings.name} because we did this alone once.` : "";
  const text = settings
    ? settings.about_text ||
      "Our founders were international students who learned the hard way. Our mission is to make going global clear, honest and supported."
    : "";
  return (
    <>
      <h1>{title}</h1>
      <p className="lead">{text}</p>
    </>
  );
}
