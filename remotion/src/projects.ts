// Text for the promo videos. Facts only: every message shown on screen is real output from
// the projects (demo runs or tests); numbers are the real test counts and measurements.

export type ProjectId = "fridge-alert-bot" | "hotel-ai-concierge" | "uptime-monitor";

export type PromoData = {
  id: ProjectId;
  index: string;
  title: string;
  summary: string;
  problem: string[];
  result: string[];
  stack: string[];
};

export const projects: Record<ProjectId, PromoData> = {
  "fridge-alert-bot": {
    id: "fridge-alert-bot",
    index: "01",
    title: "Fridge Alert Bot",
    summary: "Telegram alerts when a restaurant fridge stays too warm.",
    problem: [
      "A fridge warms up overnight.",
      "Food is spoiled by morning.",
      "Nobody was told in time.",
    ],
    result: [
      "Alert after 5 minutes above the limit; one door opening never alerts",
      "One alert per incident, then “back to normal”",
      "False alarms in the simulator: 8.2 → 0.13 per day",
      "69 automated tests",
    ],
    stack: ["Python", "FastAPI", "aiogram 3", "SQLite", "matplotlib"],
  },
  "hotel-ai-concierge": {
    id: "hotel-ai-concierge",
    index: "02",
    title: "Hotel AI Concierge",
    summary: "Answers guests in four languages from the hotel's own facts.",
    problem: [
      "Reception answers the same questions all day.",
      "In four languages.",
      "A chatbot that invents answers is worse than none.",
    ],
    result: [
      "Answers only from the hotel's knowledge base",
      "Unknown questions go to staff, the reply comes back translated",
      "EN · RU · TR · DE",
      "57 automated tests, offline demo without an API key",
    ],
    stack: ["Python", "aiogram 3", "Claude / OpenAI", "SQLite"],
  },
  "uptime-monitor": {
    id: "uptime-monitor",
    index: "03",
    title: "Uptime Monitor",
    summary: "Tells you in Telegram the minute a camera or router goes down.",
    problem: [
      "A camera stops recording.",
      "The Wi-Fi in the lobby goes down.",
      "Someone notices days later.",
    ],
    result: [
      "Ping + TCP checks for every device, every minute",
      "Alerts on down and up, with the downtime",
      "Uptime for 24 hours and 7 days on a status page",
      "45 automated tests, including real Windows and Linux ping output",
    ],
    stack: ["Python asyncio", "FastAPI", "HTMX", "aiogram 3", "SQLite"],
  },
};
