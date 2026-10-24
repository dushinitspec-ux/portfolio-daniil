// Personal details in one place. Values in [brackets] are placeholders: replace them before
// publishing. Links whose value still starts with "[" are shown as plain text, not as links.
export const site = {
  name: "Daniil Dushin",
  url: (process.env.NEXT_PUBLIC_SITE_URL ?? "https://daniildushin.dev").replace(/\/$/, ""),
  email: "dushin.itspec@gmail.com",
  telegram: "https://t.me/daniil_dushin",
  linkedin: "[LinkedIn link]", // e.g. https://www.linkedin.com/in/your-profile
  github: "https://github.com/dushinitspec-ux",
  sourceCode: "[GitHub link]/portfolio-daniil", // e.g. https://github.com/dushinitspec-ux/portfolio-daniil
} as const;

export function isPlaceholder(value: string): boolean {
  return value.startsWith("[");
}

export const cvFiles = [
  { id: "aiDeveloper", file: "/cv/daniil-dushin-cv-ai-developer.pdf" },
  { id: "itSupport", file: "/cv/daniil-dushin-cv-it-support.pdf" },
  { id: "sales", file: "/cv/daniil-dushin-cv-sales.pdf" },
  { id: "hospitality", file: "/cv/daniil-dushin-cv-hospitality.pdf" },
] as const;

export const categories = ["AI", "Bots", "Web", "Infrastructure"] as const;
export type Category = (typeof categories)[number];
