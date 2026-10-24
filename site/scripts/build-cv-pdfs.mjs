// Turns the CVs in ../docs/*.md into PDFs for the /cv page:
//   public/cv/daniil-dushin-cv-<name>.pdf
//
// Markdown -> HTML (marked) -> PDF (headless Chrome or Edge, already installed on most
// computers). Run it again after editing a CV:  npm run cv
// If the browser is not found, set CHROME_PATH to chrome.exe / msedge.exe / chromium.

import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { marked } from "marked";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const docs = path.resolve(root, "..", "docs");
const outDir = path.join(root, "public", "cv");
const names = ["ai-developer", "it-support", "sales", "hospitality"];

function findBrowser() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const candidates = [
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
  ];
  const found = candidates.find((p) => fs.existsSync(p));
  if (found) return found;
  for (const cmd of ["google-chrome", "chromium", "chromium-browser"]) {
    const which = spawnSync("which", [cmd], { encoding: "utf8" });
    if (which.status === 0) return which.stdout.trim();
  }
  throw new Error("Chrome or Edge not found. Set CHROME_PATH to the browser executable.");
}

function fontFace(weight) {
  const faces = ["latin", "latin-ext", "cyrillic"].map((subset) => {
    const file = path.join(root, "assets", "fonts", `inter-tight-${subset}-${weight}-normal.woff`);
    return `@font-face { font-family: "Inter Tight"; font-weight: ${weight};
      src: url("${pathToFileURL(file).href}") format("woff"); }`;
  });
  return faces.join("\n");
}

const css = `
${fontFace(400)}
${fontFace(600)}
@page { size: A4; margin: 16mm 17mm; }
* { box-sizing: border-box; }
body { font-family: "Inter Tight", "Segoe UI", Helvetica, Arial, sans-serif; color: #111;
  font-size: 10.2pt; line-height: 1.45; margin: 0; }
h1 { font-size: 26pt; font-weight: 600; letter-spacing: -0.03em; margin: 0 0 2mm; }
h1 + p { font-size: 11.5pt; margin: 0; }
h1 + p + p { color: #5E5A52; font-size: 9.2pt; margin: 1.5mm 0 0; padding-bottom: 4mm;
  border-bottom: 1.5pt solid #FF4F1F; }
h2 { font-size: 8.4pt; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em;
  color: #5E5A52; margin: 6mm 0 2mm; padding-top: 2mm; border-top: 0.5pt solid #ccc; }
p { margin: 0 0 2mm; }
ul { margin: 1mm 0 3mm; padding-left: 4.5mm; }
li { margin: 0 0 1mm; }
strong { font-weight: 600; }
em { font-style: normal; color: #5E5A52; }
a { color: inherit; }
`;

function main() {
  const browser = findBrowser();
  fs.mkdirSync(outDir, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cv-"));

  for (const name of names) {
    const markdown = fs.readFileSync(path.join(docs, `${name}.md`), "utf8");
    const html = `<!doctype html><html lang="en"><head><meta charset="utf-8">
      <title>Daniil Dushin — CV</title><style>${css}</style></head>
      <body>${marked.parse(markdown)}</body></html>`;
    const htmlFile = path.join(tmp, `${name}.html`);
    fs.writeFileSync(htmlFile, html);
    const pdfFile = path.join(outDir, `daniil-dushin-cv-${name}.pdf`);
    execFileSync(browser, [
      "--headless=new",
      "--disable-gpu",
      // A fresh profile per run: otherwise Edge hands the job to an already running
      // instance and returns at once, leaving an empty PDF behind.
      `--user-data-dir=${path.join(tmp, `profile-${name}`)}`,
      // Give the web fonts time to load before printing.
      "--virtual-time-budget=5000",
      "--no-pdf-header-footer",
      "--allow-file-access-from-files",
      `--print-to-pdf=${pdfFile}`,
      pathToFileURL(htmlFile).href,
    ], { stdio: "ignore" });
    console.log(`CV: ${path.relative(root, pdfFile)}`);
  }
  fs.rmSync(tmp, { recursive: true, force: true });
}

main();
