"use client";

import { useSettings } from "../SettingsProvider";

// B26: the "Pay with EPS" strip from the EPS merchant kit, shown in the footer while EPS is on.
// The light or dark picture follows the theme (CSS), the narrow picture is used under 640px.
export default function EpsStrip() {
  const { settings } = useSettings();
  if (settings?.gateways.eps?.enabled !== true) return null;
  return (
    <div className="wrap eps-strip">
      {(["light", "dark"] as const).map((theme) => (
        <picture key={theme} className={"eps-" + theme}>
          <source media="(max-width: 639px)" srcSet={`/payments/eps/footer-mobile-${theme}.png`} />
          <img src={`/payments/eps/footer-desktop-${theme}.png`} alt="Pay with EPS: cards, mobile wallets and internet banking" loading="lazy" />
        </picture>
      ))}
    </div>
  );
}
