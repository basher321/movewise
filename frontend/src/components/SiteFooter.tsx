import FooterBrand from "./FooterBrand";

// Cached, so the year is fixed when the page is built.
async function currentYear() {
  "use cache";
  return new Intl.DateTimeFormat("en", { year: "numeric", timeZone: "Asia/Dhaka" }).format(new Date());
}

export default async function SiteFooter() {
  const year = await currentYear();
  return (
    <footer>
      <FooterBrand year={year} />
    </footer>
  );
}
