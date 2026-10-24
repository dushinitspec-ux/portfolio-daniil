# Daniil Dushin — Portfolio

Job-search portfolio: CVs, a personal website and three small production-style projects
that solve real problems for restaurants, hotels and small offices.

## Repository structure

```
portfolio-daniil/
├── docs/        CVs for four roles + list of projects
├── site/        Portfolio website (EN / RU / TR / DE)
└── projects/
    ├── 01-fridge-alert-bot/     Fridge temperature alerts in Telegram
    ├── 02-hotel-ai-concierge/   Multilingual AI concierge for hotel guests
    └── 03-uptime-monitor/       Network and device uptime monitor
```

## Projects

| # | Project | Problem it solves | Stack |
|---|---------|-------------------|-------|
| 01 | [Fridge alert bot](projects/01-fridge-alert-bot) | Spoiled food and failed hygiene inspections | FastAPI, aiogram 3, SQLite, matplotlib |
| 02 | [Hotel AI concierge](projects/02-hotel-ai-concierge) | Reception answers the same questions all day | aiogram 3, OpenAI / Anthropic API, SQLite |
| 03 | [Uptime monitor](projects/03-uptime-monitor) | Cameras, routers or Wi-Fi go down and nobody notices | asyncio, FastAPI, HTMX, aiogram 3, SQLite |

Every project:

- runs in **demo mode** with simulated data — no hardware and no paid API keys needed;
- has tests (`pytest`) and passes linting (`ruff`);
- ships with `.env.example`, `Dockerfile` and `docker-compose.yml`;
- keeps a `BUGFIX.md` with real bugs found while building it.

## Quick start

Each project uses [uv](https://docs.astral.sh/uv/) and Python 3.12:

```bash
cd projects/01-fridge-alert-bot
cp .env.example .env
uv sync
uv run pytest
```

See the README inside each project for details.

## Contact

[placeholder: email] · [placeholder: Telegram] · [placeholder: LinkedIn]
