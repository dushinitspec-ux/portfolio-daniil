# Daniil Dushin

**AI Developer** | Python · LLM apps · Telegram bots | IT & network background | Russian native

Antalya, Türkiye · dushin.itspec@gmail.com · [Telegram @daniil_dushin](https://t.me/daniil_dushin) · [linkedin.com/in/daniil-dushin](https://www.linkedin.com/in/daniil-dushin) · [site-production-898c.up.railway.app](https://site-production-898c.up.railway.app) · [github.com/dushinitspec-ux](https://github.com/dushinitspec-ux)

## Summary

AI developer with a hands-on IT and networking background. I build Python services with LLMs
(Claude, OpenAI), Telegram bots and web apps, and every day I deploy and support an AI
computer-vision product on client sites, so I know both the code and the hardware it runs on.
I ship with AI coding agents (Claude Code, OpenAI Codex) and verify everything myself:
10 public projects, more than 1,300 automated tests, CI on every push and live demos that run
in the browser. My recent work targets what European businesses need now: GDPR-safe use of
LLMs, structured e-invoicing (EN 16931 / XRechnung), accessibility (WCAG 2.2) and network
asset inventories (NIS2).

## Experience

**Technical Specialist — Steady Control** (AI-powered business monitoring), Antalya · *Oct 2026 – present*

- Deploy and support an AI computer-vision system on many client sites — hotels, cafés and
  restaurants: kitchen workflow, service quality and refrigerator temperature monitoring.
- Install, configure, diagnose and repair the hardware it runs on: IP cameras, NVR/DVR
  recorders, IoT sensors, access badges and MikroTik network equipment.

**Freelance Developer & IT Support** · *Feb 2022 – present*

- Telegram bots, websites and automation for small businesses, built with Python and AI
  coding agents.
- PC setup and repair, home and small-office networks, Wi-Fi coverage and remote support for
  many private and small-business clients.
- Portfolio of 10 projects (below): every one with a demo mode, automated tests, a
  `BUGFIX.md` of real bugs found and fixed, and a live demo that runs the project's own Python
  code in the browser (Pyodide / WebAssembly).

## Projects

**E-Invoice** — Python, FastAPI, pdfplumber, lxml, Anthropic API

- Turns a PDF invoice into an XRechnung (UBL 2.1) e-invoice, for the EU move to structured
  e-invoicing (EN 16931; in Germany every business must accept them since 1 January 2025).
- Extraction with Claude (structured output) or offline rules, then 67 EN 16931 / XRechnung
  rules with their official IDs and a plain explanation each.
- Matches the official CEN and KoSIT rules on all five sample invoices; 192 tests.
  [Case study](https://site-production-898c.up.railway.app/en/projects/e-invoice)

**Helpdesk Copilot** — Python, BM25 retrieval, Anthropic API, aiogram 3, FastAPI

- Telegram IT assistant that answers from the company's own how-tos with numbered sources;
  when it is not sure, it opens a ticket with a priority (P1–P4). Tells users they are
  talking to an AI (EU AI Act, Art. 50).
- Right document in the top 3 for 30 of 30 evaluation questions (15 of 15 held out); 110
  tests. [Case study](https://site-production-898c.up.railway.app/en/projects/helpdesk-copilot)

**PII Guard** — Python, FastAPI, HTMX, Anthropic API

- Gateway that hides personal data (e-mail, phones, IBAN, cards, EU VAT IDs, IP addresses)
  before a prompt reaches the LLM and puts it back into the answer (GDPR); mask / block /
  allow policy, audit log without values.
- A property test on 500 random texts shows no original value reaches the model; 163 tests.
  [Case study](https://site-production-898c.up.railway.app/en/projects/pii-guard)

**Hotel AI concierge** — Python, aiogram 3, Anthropic / OpenAI API

- Telegram bot that answers guests in EN, RU, TR and DE only from the hotel's knowledge
  base; unknown questions go to staff and the reply is translated back to the guest.
- Offline demo mode, 68 tests.
  [Case study](https://site-production-898c.up.railway.app/en/projects/hotel-ai-concierge)

**Also built** — each with a demo mode, tests and a case study on my site:

- **Allergen Labels** — the 14 EU allergens on every dish in four languages, confirmed by a
  chef before printing (220 tests).
- **Energy Saver** — runs boilers and EV chargers in the cheapest day-ahead slots; −29.6 %
  spot cost on 30 days of real German prices (108 tests).
- **Accessibility Check** — WCAG 2.2 checks for small business websites (European
  Accessibility Act) (208 tests).
- **Network Inventory** — asset register for office networks (NIS2): new devices, risky open
  ports (117 tests).
- **Fridge alert bot** (83 tests) and **uptime monitor** (52 tests) — Telegram alerts when a
  fridge gets too warm or a camera, router or access point goes down.
- **Portfolio website** — Next.js, TypeScript, MDX, four languages, in-browser demo runtime;
  Lighthouse accessibility, best practices and SEO 100:
  [site-production-898c.up.railway.app](https://site-production-898c.up.railway.app)

## Skills

- **AI & LLM:** Claude and OpenAI APIs, structured output, prompt engineering, retrieval
  (BM25), evaluation sets, personal-data masking, AI coding agents (Claude Code, OpenAI Codex).
- **Backend:** Python 3.12, FastAPI, aiogram 3 (Telegram Bot API), asyncio, httpx, SQLite,
  pdfplumber, lxml, Jinja2.
- **Quality:** pytest, ruff, uv, Git, GitHub Actions CI.
- **Web:** Next.js, TypeScript, Tailwind CSS, HTMX, HTML/CSS, JavaScript, Pyodide (WebAssembly).
- **Infrastructure:** MikroTik RouterOS, LAN/Wi-Fi, CCTV/NVR, IoT sensors, Windows, Railway.

## Languages

Russian — native · English — A1 (basic), studying actively and ready to learn fast on site
after relocation · Turkish — basic

**Driving licence:** category B

## Education

**Belgorod State Agrarian University** — Veterinary Medicine (specialist degree), studying on
an individual study plan.
Software development: self-taught through real projects — 10 public repositories on GitHub.

## Beyond the role

Fast learner who picks up new tools and fields quickly. Builds Telegram bots and websites,
uses AI tools for automation, has sales and client-service experience. Open to new
directions, relocation and contracts abroad.
