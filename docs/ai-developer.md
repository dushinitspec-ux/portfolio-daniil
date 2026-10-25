# Daniil Dushin

**AI Developer** | AI-assisted coding · Telegram bots · Websites · Automation | Russian native

Antalya, Türkiye · dushin.itspec@gmail.com · [Telegram @daniil_dushin](https://t.me/daniil_dushin) · [LinkedIn link] · [site-production-898c.up.railway.app](https://site-production-898c.up.railway.app) · [github.com/dushinitspec-ux](https://github.com/dushinitspec-ux)

## Summary

Self-driven developer building Telegram bots and websites for small businesses. I combine
development with real IT and networking background, so I understand both the product and
the infrastructure behind it. I build with AI coding agents (Claude Code, OpenAI Codex,
ChatGPT) to ship working products fast, and I work daily with a real AI computer-vision
product in the field. My recent projects target what European businesses need now:
GDPR-safe use of LLMs, structured e-invoicing, accessibility and network asset inventories.

## Projects

**E-Invoice** — Python, FastAPI, pdfplumber, lxml, Anthropic API

- Turns a PDF invoice into an XRechnung (UBL 2.1) e-invoice, for the EU move to structured
  e-invoicing (EN 16931; in Germany every business must accept them since 1 January 2025).
- Extraction with Claude (structured output) or offline rules, then 67 EN 16931 / XRechnung
  rules with their official IDs and a plain explanation each.
- Matches the official CEN and KoSIT rules on all five sample invoices; 180 tests.
  [Case study](https://site-production-898c.up.railway.app/en/projects/e-invoice)

**Helpdesk Copilot** — Python, BM25 retrieval, Anthropic API, aiogram 3, FastAPI

- Telegram IT assistant that answers from the company's own how-tos with numbered sources;
  when it is not sure, it opens a ticket with a priority (P1–P4). Tells users they are
  talking to an AI (EU AI Act, Art. 50).
- Right document in the top 3 for 30 of 30 evaluation questions (15 of 15 held out); 95
  tests. [Case study](https://site-production-898c.up.railway.app/en/projects/helpdesk-copilot)

**PII Guard** — Python, FastAPI, HTMX, Anthropic API

- Gateway that hides personal data (e-mail, phones, IBAN, cards, EU VAT IDs, IP addresses)
  before a prompt reaches the LLM and puts it back into the answer (GDPR); mask / block /
  allow policy, audit log without values.
- A property test on 500 random texts shows no original value reaches the model; 152 tests.
  [Case study](https://site-production-898c.up.railway.app/en/projects/pii-guard)

**Hotel AI concierge** — Python, aiogram 3, Anthropic / OpenAI API

- Telegram bot that answers guests in EN, RU, TR and DE only from the hotel's knowledge
  base; unknown questions go to staff and the reply is translated back to the guest.
- Offline demo mode, 57 tests. [Result with a real hotel, if any]
  [Case study](https://site-production-898c.up.railway.app/en/projects/hotel-ai-concierge)

**Also built** — each with a demo mode, tests and a case study on my site:

- **Allergen Labels** — the 14 EU allergens on every dish in four languages, confirmed by a
  chef before printing (207 tests).
- **Energy Saver** — runs boilers and EV chargers in the cheapest day-ahead slots; −29.6 %
  spot cost on 30 days of real German prices (100 tests).
- **Accessibility Check** — WCAG 2.2 checks for small business websites (European
  Accessibility Act) (200 tests).
- **Network Inventory** — asset register for office networks (NIS2): new devices, risky open
  ports (107 tests).
- **Fridge alert bot** (69 tests) and **uptime monitor** (45 tests) — Telegram alerts when a
  fridge gets too warm or a camera, router or access point goes down.
- **HookahPlace Lara website** (hookahplacelara.com) — [Add: what it does, result]
- **Portfolio website** — Next.js, TypeScript, MDX, four languages:
  [site-production-898c.up.railway.app](https://site-production-898c.up.railway.app)

## Experience

**Technical Specialist — Steady Control** (AI-powered business monitoring), Antalya · *Oct 2026 – present*

- Deploy and support an AI computer-vision system for hotels, cafes and restaurants; install
  and maintain the cameras, recorders, sensors and network equipment it runs on.

**Freelance web development & IT support** · *Feb 2022 – present*

## Skills

Telegram Bot API, Python (FastAPI, aiogram 3, pytest), HTML/CSS, JavaScript, React
Native/Expo (learning), Git, AI-assisted development (Claude Code, OpenAI Codex, ChatGPT),
AI automation, LLM APIs (structured output), retrieval (BM25) and evaluation sets, PDF and
XML processing (pdfplumber, lxml), SQLite.

## Languages

Russian — native · English — A1 (basic), studying actively and ready to learn fast on site
after relocation · Turkish — basic

**Driving licence:** category B

## Education

[Degree, university, years]

## Beyond the role

Fast learner who picks up new tools and fields quickly. Builds Telegram bots and websites,
uses AI tools for automation and content, has sales and client-service experience, drives
(licence B). Open to new directions, relocation and contracts abroad.
