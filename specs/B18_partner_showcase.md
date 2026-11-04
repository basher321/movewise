Spec B18 - B2B partners: records, logos and an "Our partners" section per module

Purpose
The company is a B2B partner of other organisations (universities, colleges, employers,
recruitment firms, training and exam bodies). Staff keep these partners with their logo and
branding, and visitors see them on the page of the module they belong to.
Owner decisions 2026-11-02:
- A separate admin tab "Partners", apart from the "Agents" tab of B16. Agents (who refer
  applicants and earn commission) are never shown on the website; partners can be.
- Shown on all three module pages: Training (/courses), Student Consultancy (/consultancy)
  and Job Processing (/jobs).
- Never mixed: every partner belongs to exactly one module and appears only on that module's
  page. The same organisation in two modules is two partner records.

Scope
In scope:
- db/migrations/0015_partners.sql: tables partners and partner_logos.
- backend/app/routers/partners.py (new): public list and logo, admin endpoints;
  backend/app/main.py includes it. Logo checks reuse backend/app/files.py (type sniffing and
  the 2 MB limit).
- backend/tests/test_partners.py (new).
- frontend/src/lib/api: types Partner, PublicPartner, PartnerType, and listPublicPartners(),
  listPartners(), createPartner(), updatePartner(), uploadPartnerLogo(), clearPartnerLogo()
  (mock and http).
- frontend: new admin tab "Partners" (src/components/admin/PartnersTab.tsx, entry in
  src/lib/admin/tabs.ts); new public component src/components/PartnerStrip.tsx placed on the
  /courses, /consultancy and /jobs pages.
Out of scope: partner sign-in, partner detail pages, linking partners to universities,
vacancies or courses, any partner on Home, About or Contact, sliders or animation packages.

Database (0015_partners.sql)
- partners: id uuid PK, created_at, updated_at (trigger),
  module text NOT NULL CHECK (module IN ('course','study','job')),
  partner_type text NOT NULL CHECK (partner_type IN ('university','college','employer',
    'recruitment_agency','training_body','exam_board','other')),
  name text NOT NULL CHECK (btrim(name) <> '' AND length(name) <= 120),
  country text NOT NULL DEFAULT '' CHECK (length(country) <= 80),
  website text NOT NULL DEFAULT '' CHECK (website = '' OR website LIKE 'https://%'),
  description text NOT NULL DEFAULT '' CHECK (length(description) <= 300),
  contact_name text NOT NULL DEFAULT '' CHECK (length(contact_name) <= 120),
  contact_email text NOT NULL DEFAULT '' CHECK (length(contact_email) <= 254),
  contact_phone text NOT NULL DEFAULT '' CHECK (length(contact_phone) <= 40),
  agreement_ref text NOT NULL DEFAULT '' CHECK (length(agreement_ref) <= 120),
  agreement_until date NULL,
  logo_id uuid NULL FK partner_logos ON DELETE RESTRICT (indexed),
  show_on_site boolean NOT NULL DEFAULT false,
  sort_order integer NOT NULL DEFAULT 0,
  active boolean NOT NULL DEFAULT true.
  Index on (module, active, show_on_site, sort_order).
  Contact fields and the agreement are internal and never shown publicly.
- partner_logos: like branding_images (0002): id uuid PK, created_at, mime CHECK IN
  ('image/png','image/jpeg','image/webp'), size_bytes > 0, sha256, bytes bytea. Rows are only
  added; changing or clearing a logo moves logo_id and keeps the old row. A trigger blocks
  DELETE.
- No DELETE, DROP or TRUNCATE anywhere. Partners are switched off with active = false.

Contract (all under /api; P = public, SA = super admin, AD = admin of the partner's module)
PartnerType = "university" | "college" | "employer" | "recruitment_agency" | "training_body"
  | "exam_board" | "other"
PublicPartner: { id, name, partner_type, country, website, description, logo_url: string|null }
Partner: PublicPartner + { module, contact_name, contact_email, contact_phone, agreement_ref,
  agreement_until, show_on_site, sort_order, active, created_at }
- GET  /partners?module=course|study|job  P -> PublicPartner[]
  Module licensed first (MODULE_NOT_LICENSED). Only active rows with show_on_site, of that
  module only, ordered by sort_order then name.
- GET  /partners/{id}/logo  P -> the image (Cache-Control like /branding/{kind}); NOT_FOUND
  when the partner is not public or has no logo, or its module is not licensed.
- GET  /admin/partners  SA, AD  ?module, q, active -> Partner[] (an admin: own sections only)
- POST /admin/partners  SA, AD  body without id/logo/created_at -> Partner
- PUT  /admin/partners/{id}  SA, AD  same body -> Partner (an admin cannot move a partner to a
  module outside their sections)
- PUT  /admin/partners/{id}/logo  SA, AD  multipart file -> Partner (PNG, JPEG or WebP, at
  most 2 MB, checked by content, not by name)
- POST /admin/partners/{id}/logo/clear  SA, AD -> Partner
Errors as always: UNAUTHENTICATED 401, FORBIDDEN 403, MODULE_NOT_LICENSED 403, NOT_FOUND 404,
VALIDATION 422 (with a field message). Every change writes one audit row in the same
transaction: partner.created, partner.updated, partner.logo_set, partner.logo_cleared.

Frontend
- PartnerStrip (props: module): a section "Our partners" with a short line ("Universities and
  colleges we work with." / "Employers and recruitment partners we work with." / "Training and
  exam partners we work with."), and a grid of cards in the reference card style: the logo
  (contained, fixed height, light tile so dark-on-transparent logos stay visible in dark mode)
  or, without a logo, the .ico tile with the first letter; name; country and type in muted
  text. A card with a website opens it in a new tab (rel noopener). The whole section is not
  shown when the list is empty or fails to load. Uses the page's own accent (--a).
- Placed on /courses, /consultancy and /jobs before the final call-to-action, each calling
  listPublicPartners with its own module only.
- Admin tab "Partners" (admin accent #7C3AED): module filter (only licensed sections the person
  may see), search, active filter; table (logo, name, type, country, on website, agreement
  until, active); "Add partner" and edit in the existing FormDialog; logo upload with preview
  and "Remove logo" (like the Settings logo); up / down for the order.
- Works at 390px with no horizontal scroll, in light and dark mode.

Acceptance criteria
- b146 Super admin creates a study partner with a logo and show_on_site; GET /partners?module=
  study lists it with logo_url; module=job and module=course do not.
- b147 A partner with show_on_site false, or active false, is not public and its logo is
  NOT_FOUND publicly.
- b148 With the job module unlicensed, GET /partners?module=job is MODULE_NOT_LICENSED and the
  Jobs page shows no partner section.
- b149 An admin of study can manage study partners only; a job partner is FORBIDDEN for them.
- b150 A logo that is not PNG/JPEG/WebP by content, or larger than 2 MB, is VALIDATION; a new
  logo keeps the old partner_logos row; DELETE on partner_logos is blocked.
- b151 No public response contains contact fields or the agreement.
- b152 Every change writes exactly one audit row.
- All earlier tests still pass.

Assumptions
- Partner logos are used with the partner's permission; that is the owner's responsibility.
