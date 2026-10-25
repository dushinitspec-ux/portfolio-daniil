# Daniil Dushin — Portfolio

[![CI](https://github.com/dushinitspec-ux/portfolio-daniil/actions/workflows/ci.yml/badge.svg)](https://github.com/dushinitspec-ux/portfolio-daniil/actions/workflows/ci.yml)

AI Developer & IT/Network Technician based in Antalya, open to relocation.
I build AI tools that save businesses time — and I set up the hardware they run on.

**Website:** [site-production-898c.up.railway.app](https://site-production-898c.up.railway.app) · **Email:** dushin.itspec@gmail.com · [LinkedIn link]

This repository holds everything an employer needs in one place: CVs, the portfolio website,
ten production-style projects and promo videos for the first three.

## Projects

| # | Project | Problem it solves | Stack | Tests | Live demo |
|---|---------|-------------------|-------|-------|-----------|
| 01 | [Fridge Alert Bot](projects/01-fridge-alert-bot) | Spoiled food and failed hygiene inspections | FastAPI, aiogram 3, SQLite, matplotlib | 83 | [Run](https://site-production-898c.up.railway.app/en/projects/fridge-alert-bot/demo) |
| 02 | [Hotel AI Concierge](projects/02-hotel-ai-concierge) | Reception answers the same questions all day, in four languages | aiogram 3, Claude / OpenAI API, SQLite | 68 | [Run](https://site-production-898c.up.railway.app/en/projects/hotel-ai-concierge/demo) |
| 03 | [Uptime Monitor](projects/03-uptime-monitor) | Cameras, routers or Wi-Fi go down and nobody notices | asyncio, FastAPI, HTMX, aiogram 3, SQLite | 52 | [Run](https://site-production-898c.up.railway.app/en/projects/uptime-monitor/demo) |
| 04 | [PII Guard](projects/04-pii-guard) | Staff paste customers' personal data into AI chats (GDPR) | FastAPI, HTMX, Claude API, phonenumbers, SQLite | 163 | [Run](https://site-production-898c.up.railway.app/en/projects/pii-guard/demo) |
| 05 | [E-Invoice](projects/05-e-invoice) | PDF invoices while the EU moves to structured e-invoices (EN 16931, XRechnung) | FastAPI, pdfplumber, lxml, Claude API, SQLite | 192 | [Run](https://site-production-898c.up.railway.app/en/projects/e-invoice/demo) |
| 06 | [Helpdesk Copilot](projects/06-helpdesk-copilot) | IT support answers the same questions; answers must come from the company's own how-tos | aiogram 3, BM25, Claude API, FastAPI, SQLite | 110 | [Run](https://site-production-898c.up.railway.app/en/projects/helpdesk-copilot/demo) |
| 07 | [Network Inventory](projects/07-network-inventory) | Nobody knows what is on the office network (NIS2 asset management) | asyncio, FastAPI, aiogram 3, SQLite | 117 | [Run](https://site-production-898c.up.railway.app/en/projects/network-inventory/demo) |
| 08 | [Accessibility Check](projects/08-accessibility-check) | Online shops fall under the European Accessibility Act since June 2025 | httpx, BeautifulSoup, FastAPI, Claude API, SQLite | 208 | [Run](https://site-production-898c.up.railway.app/en/projects/accessibility-check/demo) |
| 09 | [Energy Saver](projects/09-energy-saver) | Boilers and EV chargers run in the most expensive hours of the day-ahead market | asyncio, FastAPI, aiogram 3, SQLite | 108 | [Run](https://site-production-898c.up.railway.app/en/projects/energy-saver/demo) |
| 10 | [Allergen Labels](projects/10-allergen-labels) | Menus must declare the 14 EU allergens, in the guests' languages | FastAPI, Jinja2, Claude API, SQLite | 220 | [Run](https://site-production-898c.up.railway.app/en/projects/allergen-labels/demo) |

Every project is also published as its own repository: [fridge-alert-bot](https://github.com/dushinitspec-ux/fridge-alert-bot) · [hotel-ai-concierge](https://github.com/dushinitspec-ux/hotel-ai-concierge) · [uptime-monitor](https://github.com/dushinitspec-ux/uptime-monitor) · [pii-guard](https://github.com/dushinitspec-ux/pii-guard) · [e-invoice](https://github.com/dushinitspec-ux/e-invoice) · [helpdesk-copilot](https://github.com/dushinitspec-ux/helpdesk-copilot) · [network-inventory](https://github.com/dushinitspec-ux/network-inventory) · [accessibility-check](https://github.com/dushinitspec-ux/accessibility-check) · [energy-saver](https://github.com/dushinitspec-ux/energy-saver) · [allergen-labels](https://github.com/dushinitspec-ux/allergen-labels).

Every project:

- runs in **demo mode** with simulated or bundled sample data — no hardware and no paid API keys needed;
- has a **live demo in the browser**: the project's own Python code runs on the visitor's device (Pyodide), plays a short scenario, then lets you try it;
- has tests (`pytest`) and passes linting (`ruff`), checked by GitHub Actions on every push;
- ships with `.env.example`, `Dockerfile` and `docker-compose.yml`;
- keeps a `BUGFIX.md` with the real bugs found while building it (root cause, fix, before/after code).

![Uptime Monitor status page in demo mode](projects/03-uptime-monitor/docs/status-page.jpg)

## Repository structure

```
portfolio-daniil/
├── docs/        CVs for four kinds of roles and the project list
├── site/        Portfolio website: Next.js 14, TypeScript, Tailwind, MDX, EN/RU/TR/DE
├── remotion/    Cover images for every project and promo videos for 01–03 (Remotion, React)
└── projects/
    ├── 01-fridge-alert-bot/
    ├── 02-hotel-ai-concierge/
    ├── 03-uptime-monitor/
    ├── 04-pii-guard/
    ├── 05-e-invoice/
    ├── 06-helpdesk-copilot/
    ├── 07-network-inventory/
    ├── 08-accessibility-check/
    ├── 09-energy-saver/
    └── 10-allergen-labels/
```

## Quick start

Python projects use [uv](https://docs.astral.sh/uv/) and Python 3.12:

```bash
cd projects/01-fridge-alert-bot
cp .env.example .env
uv sync
uv run pytest
```

The website needs Node.js 22:

```bash
cd site
npm install
npm run dev
```

See the README inside each folder for details.

## How I work

I build with AI coding agents and check everything myself: each project runs end to end,
has automated tests, and documents the real bugs I hit — including the ones that only
appeared on a real network or a non-English Windows.

## Contact

dushin.itspec@gmail.com · [Telegram](https://t.me/daniil_dushin) · [LinkedIn link] · [GitHub](https://github.com/dushinitspec-ux)
