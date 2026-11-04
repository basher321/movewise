Spec F01 - Frontend shell and design system

Purpose
Create the Next.js frontend skeleton that looks exactly like reference/nextgen-learning-v2.html:
the same colours, fonts, header, footer, buttons, cards and page layouts. Later specs fill these
pages with real behaviour. This spec builds only the empty, styled frame.

Scope
In scope:
- A new Next.js app (App Router, TypeScript strict) in frontend/.
- Global CSS that copies the reference design tokens and shared classes (.wrap, .btn, .btn.ghost,
  .btn.sm, .card, .grid, .tag, .bd, .hero, .vis, .band, .road, .cta, .chips, .head, .lead, .stats,
  .two, .list, .seg, dialog styles, footer) with the same values as the reference.
- Fonts Sora and DM Sans through next/font.
- The logo image extracted from the reference file into frontend/public/logo.png.
- Shared components: SiteHeader, SiteFooter, PageShell (sets the page accent colour), Button,
  Card, Tag, Badge, Modal (wraps the HTML dialog element), EmptyState.
- A default company config file frontend/src/config/company.ts holding the values shown in the
  reference (name, tagline, address, hours, email, phone, facebook, logo path). Later this comes
  from Settings; for now components read it from this one file only.
- Route skeletons with the static content of the reference for these pages:
  /                Home
  /courses         Courses list (static cards from the reference)
  /consultancy     Student Consultancy (static sections, agent area left as an empty card)
  /jobs            Job Processing (static sections, agent area left as an empty card)
  /about           About Us
  /contact         Contact (form shown but not connected)
  /verify          Certificate check (form shown but not connected)
  /profile         Placeholder card "My profile - coming in a later step"
  /admin           Placeholder card "Admin panel - coming in a later step"
Out of scope: data, the api layer, sign in, payments, licence logic, settings logic, AI agents,
dialog behaviour other than open/close. These come in later specs.

Contract
- Header: logo on the left (links to /), menu in the middle with Home, Courses,
  Student Consultancy, Job Processing, About Us, Contact, and Sign in / Sign up buttons on the
  right (they open an empty Modal for now). The current page's menu item is highlighted
  exactly as in the reference.
- Footer: "© <year> <company name>. All rights reserved." on the left; on the right
  "Verify certificate · Facebook · Student login · Admin panel" links.
- PageShell props: accent (one of the section colours in CLAUDE.md), children.
- Button props: variant "primary" | "ghost", size "md" | "sm", href (renders a link) or onClick.
- Badge props: tone "default" | "ok" | "warn" | "no" | "info", children.
- Modal props: open, title, onClose, children. Closes on the X button, on Escape and on a
  click outside the box.

Functional rules
- Text, headings and section order on each page are copied from the reference, not invented.
- The company name, address, hours, email, phone and Facebook link are read only from
  src/config/company.ts.
- Light and dark mode follow the user's system setting, using the same token values as the
  reference.
- The menu scrolls sideways on small screens exactly like the reference (it does not wrap into
  a hamburger).

Edge cases
- If the logo file is missing, the header shows the company name as text instead of a broken image.
- An unknown route shows a simple "Page not found" card with a "Go home" button, in the same style.

Non-functional rules
- No UI or CSS framework, no state library, no extra packages beyond what create-next-app adds.
- No page may scroll sideways at 390px width.
- Pages use semantic HTML (header, nav, main, section, footer) and every button has a label.
- npm run build and npm run lint must pass with zero errors.

Acceptance criteria
- npm run build passes and npm run lint shows no errors.
- npm run dev shows the Home page with the same header, hero, "Three ways we help you" cards,
  "How it works" band, "Popular right now", testimonials, call-to-action and footer as the
  reference.
- Each route in Scope opens and shows its static content; the current menu item is highlighted.
- Changing the name in src/config/company.ts changes it in the header alt text, footer and
  contact card without touching any page file.
- At 390px width no page scrolls sideways.
- With the system in dark mode, background and text use the reference dark tokens.
- Sign in / Sign up open an empty Modal that closes with X, Escape and outside click.
- An unknown address shows the "Page not found" card.

Assumptions
- Node.js 20 or newer and npm are installed.
- reference/nextgen-learning-v2.html exists and is the only design source.
