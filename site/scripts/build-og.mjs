// Generates the Open Graph preview images (1200 x 630 PNG) before `next build`:
//   public/og/<locale>/default.png             - home page and other pages
//   public/og/<locale>/projects/<slug>.png      - one per case study
//
// Why a script and not Next.js `opengraph-image.tsx`: the image renderer bundled with
// Next.js 14 cannot load on Windows (it builds file URLs with path.join), so the build
// failed there. A plain Node script works the same on Windows, macOS and Vercel.

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { Resvg } from "@resvg/resvg-js";
import matter from "gray-matter";
import satori from "satori";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const locales = ["en", "ru", "tr", "de"];
const SIZE = { width: 1200, height: 630 };
const COLORS = { bg: "#F5F3EE", fg: "#111111", muted: "#5E5A52", accent: "#FF4F1F" };

async function loadFonts() {
  const dir = path.join(root, "assets", "fonts");
  const fonts = [];
  for (const subset of ["latin", "latin-ext", "cyrillic"]) {
    for (const weight of [400, 600]) {
      const file = path.join(dir, `inter-tight-${subset}-${weight}-normal.woff`);
      // A separate family name per subset: satori only falls back between different families.
      fonts.push({ name: `Inter Tight ${subset}`, data: await fs.readFile(file), weight, style: "normal" });
    }
  }
  return fonts;
}

// satori takes React-like element objects; this keeps the script free of JSX.
const h = (type, style, ...children) => ({ type, props: { style, children } });

function card({ label, title, footer }) {
  // In satori padding is added on top of width: 100%, so the spacing is a margin on an inner
  // box that fills the card, otherwise the content would overflow the right and bottom edges.
  const inner = h(
    "div",
    {
      display: "flex",
      flexDirection: "column",
      justifyContent: "space-between",
      flexGrow: 1,
      margin: "64px 72px",
    },
    h(
      "div",
      {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        borderBottom: "1px solid rgba(17,17,17,0.2)",
        paddingBottom: 20,
        fontSize: 24,
        color: COLORS.muted,
      },
      h("div", { display: "flex" }, label),
      h("div", { width: 18, height: 18, background: COLORS.accent }),
    ),
    h(
      "div",
      {
        display: "flex",
        fontSize: title.length > 60 ? 64 : title.length > 30 ? 80 : 104,
        fontWeight: 600,
        lineHeight: 1.02,
        letterSpacing: "-0.045em",
        maxWidth: 1050,
      },
      title,
    ),
    h("div", { display: "flex", fontSize: 26, color: COLORS.muted }, footer),
  );
  return h(
    "div",
    {
      width: "100%",
      height: "100%",
      display: "flex",
      background: COLORS.bg,
      color: COLORS.fg,
      fontFamily: "Inter Tight latin, Inter Tight latin-ext, Inter Tight cyrillic",
    },
    inner,
  );
}

async function render(element, fonts, outFile) {
  const svg = await satori(element, { ...SIZE, fonts });
  const png = new Resvg(svg, { fitTo: { mode: "width", value: SIZE.width } }).render().asPng();
  await fs.mkdir(path.dirname(outFile), { recursive: true });
  await fs.writeFile(outFile, png);
}

async function main() {
  const fonts = await loadFonts();
  const contentDir = path.join(root, "content", "projects");
  const files = await fs.readdir(contentDir);
  const outDir = path.join(root, "public", "og");
  let count = 0;

  for (const locale of locales) {
    const messages = JSON.parse(
      await fs.readFile(path.join(root, "messages", `${locale}.json`), "utf8"),
    );
    const { home, projects } = messages;

    await render(
      card({
        label: `Daniil Dushin · ${home.role}`,
        title: home.headline,
        footer: `${home.place} · ${home.available}`,
      }),
      fonts,
      path.join(outDir, locale, "default.png"),
    );
    count++;

    for (const file of files.filter((f) => f.endsWith(`.${locale}.mdx`))) {
      const slug = file.slice(0, -`.${locale}.mdx`.length);
      const { data } = matter(await fs.readFile(path.join(contentDir, file), "utf8"));
      await render(
        card({
          label: `${projects.title} · ${String(data.order).padStart(2, "0")}`,
          title: data.title,
          footer: `Daniil Dushin · ${data.stack.slice(0, 3).join(" · ")}`,
        }),
        fonts,
        path.join(outDir, locale, "projects", `${slug}.png`),
      );
      count++;
    }
  }
  console.log(`Open Graph images: ${count} written to public/og`);
}

await main();
