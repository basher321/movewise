import FooterBrand from "./FooterBrand";
import EpsStrip from "./payment/EpsStrip";

// Cached, so the year is fixed when the page is built.
async function currentYear() {
  "use cache";
  return new Intl.DateTimeFormat("en", { year: "numeric", timeZone: "Asia/Dhaka" }).format(new Date());
}

export default async function SiteFooter() {
  const year = await currentYear();
  return (
    <footer>
      <EpsStrip />
      <FooterBrand year={year} />
    </footer>
  );
}
