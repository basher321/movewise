import type { Metadata, Viewport } from "next";
import { DM_Sans, Sora } from "next/font/google";
import SiteFooter from "@/components/SiteFooter";
import SessionProvider from "@/components/SessionProvider";
import SettingsProvider from "@/components/SettingsProvider";
import SiteHeader from "@/components/SiteHeader";
import "./globals.css";

const sora = Sora({
  variable: "--font-sora",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
});

// The company name comes from Settings in the browser; SettingsProvider adds it to the title.
export const metadata: Metadata = {
  title: "Home",
  // Same fallback logo as the header; SettingsProvider swaps in the Settings logo when one is set.
  icons: { icon: "/logo.png" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sora.variable} ${dmSans.variable}`}>
      <body>
        <SettingsProvider>
          <SessionProvider>
            <SiteHeader />
            <main>{children}</main>
            <SiteFooter />
          </SessionProvider>
        </SettingsProvider>
      </body>
    </html>
  );
}
