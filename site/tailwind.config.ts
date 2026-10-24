import type { Config } from "tailwindcss";

// Colours are CSS variables (see app/globals.css), so light and dark mode share one set of
// class names and the dark palette is defined in a single place.
const color = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: color("bg"),
        fg: color("fg"),
        muted: color("muted"),
        surface: color("surface"),
        accent: color("accent"),
        "accent-text": color("accent-text"),
      },
      borderColor: {
        line: "rgb(var(--fg) / 0.14)",
        strong: "rgb(var(--fg) / 0.9)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      fontSize: {
        label: ["0.75rem", { lineHeight: "1.2", letterSpacing: "0.02em" }],
      },
      maxWidth: {
        page: "90rem",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.2, 0.7, 0.1, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
