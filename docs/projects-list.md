# Portfolio projects

Ten projects aimed at employers' main pains. Employers pay to save staff time, stop losing
clients and money, and see problems before they cost them. Each project hits one of these
pains.

For each one: build it, test it end to end, record a one-minute demo video, and put the code
on GitHub with a README.

| # | Project | Pain it solves | Status |
|---|---------|----------------|--------|
| 1 | Fridge temperature alert bot | Spoiled food and failed inspections | **Built** — [projects/01-fridge-alert-bot](../projects/01-fridge-alert-bot) |
| 2 | AI hotel concierge | Reception overloaded with repeated questions | **Built** — [projects/02-hotel-ai-concierge](../projects/02-hotel-ai-concierge) |
| 3 | Restaurant booking bot + admin panel | Lost bookings by phone | Planned |
| 4 | Lead capture landing + CRM bot | Leads from the site get lost | Planned |
| 5 | Customer review analyzer | Owners don't know why clients are unhappy | Planned |
| 6 | Staff shift and task checklist bot | Staff skip routine tasks | Planned |
| 7 | Network and device uptime monitor | Cameras or Wi-Fi go down and nobody notices | **Built** — [projects/03-uptime-monitor](../projects/03-uptime-monitor) |
| 8 | AI document and invoice parser | Hours of manual data entry | Planned |
| 9 | Sales chatbot for an online shop | Buyers leave without asking | Planned |
| 10 | Personal portfolio site | The employer needs to see everything in 30 seconds | **Built** — [site](../site) |

## Rules for every project

Write clean, commented code. Add a README in English with: the business problem, features,
screenshots placeholder, setup steps, and environment variables in `.env.example`. Add basic
error handling and logging. Include a Dockerfile. No hard-coded secrets.

Before showing any project: run it yourself end to end, fix every error, and record the demo.
AI writes the code fast, but the checking is your job, and that is exactly what interviewers
will ask about.

## Prompts for the planned projects

**3. Restaurant booking bot + admin panel.** "Build a booking system: Telegram bot for guests
(pick date, time, number of people), FastAPI backend, PostgreSQL, and a simple web admin page
to view and confirm bookings. Send reminders 2 hours before. Prevent double booking of
tables."

**4. Lead capture landing + CRM bot.** "Build a modern responsive landing page (HTML,
Tailwind) for a local service business with a lead form. Leads go to a backend, are saved in
a database, and are sent to a Telegram bot where the manager can mark status: new, in
progress, closed. Add a weekly report of leads by status."

**5. Customer review analyzer.** "Build a Python web app (Streamlit) that loads customer
reviews from CSV, uses an LLM API to classify each by sentiment and topic (food, service,
price, cleanliness), and shows a dashboard with charts and the top 5 complaints. Include
sample data."

**6. Staff shift and task checklist bot.** "Build a Telegram bot for cafe staff: daily
opening/closing checklists, each step confirmed with a photo, late or missed tasks reported to
the manager, and a monthly report per employee. Use aiogram 3 and SQLite."

**8. AI document and invoice parser.** "Build a web app where the user uploads PDF or photo
invoices; the app extracts supplier, date, items and totals using an LLM API, lets the user
correct fields, and exports to Excel/CSV. Use FastAPI and a simple frontend."

**9. Sales chatbot for an online shop.** "Build a website chat widget plus backend that
answers product questions from a JSON catalog using an LLM, recommends products, and collects
the buyer's contact when they want to order. Log all chats for the owner to review."

## Where to publish the CVs

- **LinkedIn** — one profile; headline combining IT + Russian. Turn on "Open to work".
- **Habr Career / Hirify** — Russian-speaking companies, remote.
- **Upwork / Kwork** — freelance bots and websites.
- **kariyer.net** — Türkiye, hotels and IT.
- **Hotel careers pages, cruise lines, UAE hotel groups** — tourism with housing and visa.
