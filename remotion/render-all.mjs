// Renders every promo video and cover image straight into the website's public folder:
//   ../site/public/videos/<id>.mp4
//   ../site/public/projects/<id>/cover.png
//   ../site/public/projects/hotel-ai-concierge/conversation.png  (chat frame for screenshots)
//
// Usage: npm run render            (everything)
//        npm run render -- covers  (only the still images, takes seconds)

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

// Projects with a promo video; every project in coverIds gets a cover.
const ids = ["fridge-alert-bot", "hotel-ai-concierge", "uptime-monitor"];
const coverIds = [
  ...ids,
  "pii-guard",
  "e-invoice",
  "helpdesk-copilot",
  "network-inventory",
  "accessibility-check",
  "energy-saver",
  "allergen-labels",
];
const site = path.resolve("..", "site", "public");
const onlyCovers = process.argv.includes("covers");

function remotion(...args) {
  console.log(`> remotion ${args.join(" ")}`);
  const result = spawnSync("npx", ["remotion", ...args], { stdio: "inherit", shell: true });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

for (const id of coverIds) {
  const dir = path.join(site, "projects", id);
  fs.mkdirSync(dir, { recursive: true });
  remotion("still", "src/index.ts", `cover-${id}`, path.join(dir, "cover.png"));
}

// The concierge's last chat frame doubles as its screenshot. Frame = start of the screens
// scene (390) + the moment every message is on screen (450).
remotion(
  "still",
  "src/index.ts",
  "promo-hotel-ai-concierge",
  path.join(site, "projects", "hotel-ai-concierge", "conversation.png"),
  "--frame=840",
);

if (!onlyCovers) {
  fs.mkdirSync(path.join(site, "videos"), { recursive: true });
  for (const id of ids) {
    remotion("render", "src/index.ts", `promo-${id}`, path.join(site, "videos", `${id}.mp4`));
  }
}
