# Daniil Dushin — Portfolio

[![CI](https://github.com/[github-username]/portfolio-daniil/actions/workflows/ci.yml/badge.svg)](https://github.com/[github-username]/portfolio-daniil/actions/workflows/ci.yml)

AI Developer & IT/Network Technician based in Antalya, open to relocation.
I build AI tools that save businesses time — and I set up the hardware they run on.

**Website:** [Portfolio link] · **Email:** dushin.itspec@gmail.com · [LinkedIn link]

This repository holds everything an employer needs in one place: CVs, the portfolio website,
three production-style projects and the promo videos for them.

## Projects

| # | Project | Problem it solves | Stack | Tests |
|---|---------|-------------------|-------|-------|
| 01 | [Fridge Alert Bot](projects/01-fridge-alert-bot) | Spoiled food and failed hygiene inspections | FastAPI, aiogram 3, SQLite, matplotlib | 69 |
| 02 | [Hotel AI Concierge](projects/02-hotel-ai-concierge) | Reception answers the same questions all day, in four languages | aiogram 3, Claude / OpenAI API, SQLite | 57 |
| 03 | [Uptime Monitor](projects/03-uptime-monitor) | Cameras, routers or Wi-Fi go down and nobody notices | asyncio, FastAPI, HTMX, aiogram 3, SQLite | 45 |

Every project:

- runs in **demo mode** with simulated data — no hardware and no paid API keys needed;
- has tests (`pytest`) and passes linting (`ruff`), checked by GitHub Actions on every push;
- ships with `.env.example`, `Dockerfile` and `docker-compose.yml`;
- keeps a `BUGFIX.md` with the real bugs found while building it (root cause, fix, before/after code).

![Uptime Monitor status page in demo mode](projects/03-uptime-monitor/docs/status-page.jpg)

## Repository structure

```
portfolio-daniil/
├── docs/        CVs for four kinds of roles (+ Russian copies) and the project list
├── site/        Portfolio website: Next.js 14, TypeScript, Tailwind, MDX, EN/RU/TR/DE
├── remotion/    Promo videos and cover images for every project (Remotion, React)
└── projects/
    ├── 01-fridge-alert-bot/
    ├── 02-hotel-ai-concierge/
    └── 03-uptime-monitor/
```

## Quick start

Python projects use [uv](https://docs.astral.sh/uv/) and Python 3.12:

```bash
cd projects/01-fridge-alert-bot
cp .env.example .env
uv sync
uv run pytest
```

The website needs Node.js 20+:

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

dushin.itspec@gmail.com · [Telegram link] · [LinkedIn link] · [GitHub link]
