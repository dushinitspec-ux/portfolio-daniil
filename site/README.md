# Portfolio website

Personal portfolio of Daniil Dushin, AI Developer & IT/Network Technician.
Four languages (English by default, Russian, Turkish, German), case studies written in MDX,
deploy-ready for Vercel.

## Stack

- **Next.js 14** (App Router, static generation), **TypeScript**, **Tailwind CSS**
- **next-intl**: URLs `/en`, `/ru`, `/tr`, `/de`, language switcher, `hreflang` tags
- **MDX** case studies compiled at build time with `@mdx-js/mdx`; code highlighted with **Shiki**
- Motion: **GSAP + ScrollTrigger** (pinned project stack), **Lenis** (smooth scrolling),
  **Framer Motion** (page transitions, filter layout animation), CSS split-text headline
- Open Graph images rendered with **satori + resvg**; CV PDFs printed with headless Chrome/Edge
- Promo videos for every project live in [`../remotion`](../remotion)

## Run locally

```bash
npm install
npm run dev          # http://localhost:3000
npm run build        # production build (also generates Open Graph images)
npm start
```

## Add a new project in 2 minutes

1. Copy an existing case study for every language, e.g.
   `content/projects/uptime-monitor.en.mdx` → `my-project.en.mdx`, `.ru.mdx`, `.tr.mdx`, `.de.mdx`.
   The part of the file name before the language is the URL: `/en/projects/my-project`.
2. Edit the frontmatter: `title`, `summary`, `categories` (any of `AI`, `Bots`, `Web`,
   `Infrastructure`), `order`, `featured`, `stack`, `github`, `demo`, `cover`, `screenshots`.
3. Put images in `public/projects/my-project/` and a video in `public/videos/` (optional).
4. Write the body with these blocks; the section titles are translated automatically:

   ```mdx
   <Section id="problem">Text…</Section>
   <Section id="solution">Text…</Section>
   <Section id="demo"><Demo /></Section>
   <Section id="screenshots"><Screenshots /></Section>
   <Section id="stack"><Stack /></Section>
   <Section id="code">A fenced code block, highlighted with a copy button</Section>
   <Section id="bug">
     ### Title of the bug
     <BugPart id="problem">…</BugPart>
     <BugPart id="cause">…</BugPart>
     <BugPart id="fix">…</BugPart>
     <Diff> two fenced code blocks: before, then after </Diff>
   </Section>
   <Section id="result">…</Section>
   <Section id="links"><Links /></Section>
   ```

5. `npm run build`. The build fails with a clear message if a translation is missing or the
   frontmatter has a typo, so a broken page can never be deployed.

## Other scripts

| Command | What it does |
|---|---|
| `npm run og` | Renders Open Graph images into `public/og/` (also runs before every build) |
| `npm run cv` | Turns `../docs/*.md` into the PDFs on the `/cv` page. Run it after editing a CV |
| `npm run lint` / `npm run typecheck` | ESLint and TypeScript checks |

## Before publishing

- Replace the placeholders in [`lib/site.ts`](lib/site.ts) (Telegram, LinkedIn, GitHub) and the
  `[GitHub link]` / `[Live demo link]` values in the MDX frontmatter. Links that still contain
  a `[placeholder]` are shown as plain text, never as broken links.
- On Vercel set `NEXT_PUBLIC_SITE_URL` to the real domain (used for canonical URLs, `hreflang`,
  the sitemap and Open Graph links). Default: `https://daniildushin.dev`.

## Design and engineering decisions

- **Swiss / editorial layout:** a 12-column grid, 1px rules, Inter Tight with JetBrains Mono
  labels, one accent colour (`#FF4F1F`) used for shapes. For small text the accent is darkened
  to keep WCAG AA contrast. Dark mode uses the same tokens (`app/globals.css`).
- **Nothing important waits for JavaScript.** The headline reveal is pure CSS, so it plays on
  first paint. Scroll reveals hide only elements below the fold, and only once the script is
  running. An `IntersectionObserver` starts them, so they also play after anchor links,
  keyboard scrolling or find-in-page. The first page load is never animated by Framer Motion.
- **Heavy libraries load late:** GSAP, ScrollTrigger and Lenis are imported after the `load`
  event. Shiki runs at build time, so visitors download no highlighter.
- **`prefers-reduced-motion`** turns off the headline reveal, smooth scrolling, scroll
  reveals and page transitions.
- **Next.js 14** is used because the brief asks for it. Upgrading to a newer major version is a
  separate task.

## Quality checks (October 2026, local production build)

- `npm run build`: zero errors, zero warnings.
- Lighthouse, mobile profile: Accessibility 100, Best Practices 100, SEO 100 on every page
  tested; Performance 95–100 on most runs (single runs of the heaviest case-study page dropped
  to ~89 on a busy machine). Desktop: 100.
- No horizontal scrolling at 360px on any page, all four languages.

Real bugs found while building the site: [BUGFIX.md](BUGFIX.md).
