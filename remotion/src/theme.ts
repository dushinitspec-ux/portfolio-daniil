import { loadFont as loadInterTight } from "@remotion/google-fonts/InterTight";
import { loadFont as loadJetBrainsMono } from "@remotion/google-fonts/JetBrainsMono";

// Same palette and fonts as the website, so the videos feel like part of it.
export const colors = {
  bg: "#F5F3EE",
  fg: "#111111",
  muted: "#5E5A52",
  line: "rgba(17, 17, 17, 0.14)",
  surface: "#ECE9E2",
  accent: "#FF4F1F",
  green: "#22A05A",
};

export const sans = loadInterTight("normal", {
  weights: ["400", "600"],
  subsets: ["latin", "latin-ext", "cyrillic"],
}).fontFamily;

export const mono = loadJetBrainsMono("normal", {
  weights: ["400"],
  subsets: ["latin", "latin-ext", "cyrillic"],
}).fontFamily;

export const FPS = 30;
