import "server-only";

import fs from "node:fs";
import path from "node:path";

// In-browser demos are static pages in public/demos/<slug>/ (see scripts/build-demos.mjs and
// public/demos/_shared/). A project has a demo when its page exists; nothing else to register.
const DEMOS_DIR = path.join(process.cwd(), "public", "demos");

export function hasDemo(slug: string): boolean {
  return fs.existsSync(path.join(DEMOS_DIR, slug, "index.html"));
}

export function demoPath(slug: string): string {
  return `/projects/${slug}/demo`;
}
