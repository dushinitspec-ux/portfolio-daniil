# Bugs found and fixed

Real bugs I hit while building the website, in the order I found them.

---

## 1. Open Graph images broke the build on Windows

**What broke.** `npm run build` compiled every page and then failed on all 16 Open Graph
image routes:

```
TypeError: Invalid URL
    at fileURLToPath (node:internal/url:1505:12)
    at .../next/dist/compiled/@vercel/og/index.node.js:18988:32
```

**Root cause.** The image renderer bundled with Next.js 14 finds its own font file like this:

```js
fs.readFileSync(fileURLToPath(join(import.meta.url, "../noto-sans-v27-latin-regular.ttf")))
```

`join` is `path.join`, which is meant for file paths, not URLs. On Windows it turns
`file:///C:/...` into `file:\C:\...`, which is not a valid URL. On Linux (and on Vercel) the
slashes stay as they are, so the bug only shows up on Windows. The standalone `@vercel/og`
package fixes the path but fails differently when loaded from Node: `Dynamic require of "fs"
is not supported`.

**Fix.** The images no longer depend on Next.js route handlers. A small script renders them
with the same libraries the renderer uses inside (satori to SVG, resvg to PNG) before every
build, and the page metadata points to the files:

```json
// package.json — before
"build": "next build"
```

```json
// package.json — after
"prebuild": "node scripts/build-og.mjs",
"build": "next build"
```

**Lesson.** Code that builds a path out of a URL with `path.join` works on one operating
system and breaks on another. Check a dependency's source when the stack trace points into it.

---

## 2. Russian titles in the Open Graph images were empty boxes

**What broke.** The Russian preview image showed squares instead of letters.

**Root cause.** The font is loaded as three files (Latin, Latin Extended, Cyrillic), all named
"Inter Tight". satori picks the first font with a matching name and weight, the Latin one,
and does not look at the other files with the same name for missing letters.

**Fix.** Each file gets its own family name, and the card lists them as fallbacks:

```js
// before
fonts.push({ name: "Inter Tight", data, weight, style: "normal" });
fontFamily: "Inter Tight",
```

```js
// after
fonts.push({ name: `Inter Tight ${subset}`, data, weight, style: "normal" });
fontFamily: "Inter Tight latin, Inter Tight latin-ext, Inter Tight cyrillic",
```

---

## 3. Half of every Open Graph card was cut off

**What broke.** The accent square and the footer line were missing from every image, and the
divider ran into the right edge.

**Root cause.** The card had `width: 100%` plus `padding: 64px 72px`. In satori, padding is
added on top of the width, so the card was 144px wider and 128px taller than the image, and
the right and bottom parts fell outside it.

**Fix.** The outer box fills the image with no padding; an inner box with a margin holds the
content.

---

## 4. Three of the four CV PDFs were empty

**What broke.** `npm run cv` reported four PDFs, but three were 4–7 KB with no text.

**Root cause.** The script runs Edge in headless mode once per CV. Edge, like Chrome, allows
only one running instance per profile: the second call handed the job to the first instance
and exited immediately, before anything was printed.

**Fix.** Every run gets its own temporary profile, plus time for the web fonts to load:

```js
// before
execFileSync(browser, [
  "--headless=new",
  "--disable-gpu",
  "--no-pdf-header-footer",
  `--print-to-pdf=${pdfFile}`,
  url,
]);
```

```js
// after
execFileSync(browser, [
  "--headless=new",
  "--disable-gpu",
  `--user-data-dir=${path.join(tmp, `profile-${name}`)}`,
  "--virtual-time-budget=5000",
  "--no-pdf-header-footer",
  `--print-to-pdf=${pdfFile}`,
  url,
]);
```

---

## 5. The home page jumped when the font loaded (Lighthouse CLS 0.24)

**What broke.** Lighthouse measured a Cumulative Layout Shift of 0.24 on the home page
(above 0.1 counts as poor): the paragraph under the headline moved down after loading.

**Root cause.** The page first paints with a fallback font, then Inter Tight replaces it
(`font-display: swap`). Two things made that swap move the layout:

1. The headline width was `max-w-[15ch]`, and `ch` is the width of the digit "0" *in the
   current font*. When the font changed, the box width changed too.
2. Even with a fixed width, the large headline wraps differently in the two fonts and becomes
   one line taller or shorter. Everything below it moved.

**First attempt (reverted).** `display: "optional"` removes the swap: the browser uses the web
font only if it is ready within about 100 ms, otherwise it keeps the fallback for the visit.
CLS went to 0, but in real browsing the brand font often did not appear at all. A design that
depends on its typeface cannot accept that.

**Fix.**

- Widths use `em` (relative to the font size, not to a particular font).
- Fonts stay on `display: "swap"`, so the brand font always appears.
- The hero is laid out so that the headline re-wrapping moves nothing else: on desktop the
  headline is alone on the left and the portrait, intro and buttons sit in a fixed-width
  column on the right; nothing is placed under the headline.
- The monospace font gets a monospace fallback (`next/font` defaults to an adjusted Arial),
  so labels keep their width and look during the swap.

```tsx
// before
className="max-w-[15ch] ..."
// intro and buttons under the headline
```

```tsx
// after
className="max-w-[8.4em] ..."
// <div className="md:flex"> headline | <div className="md:w-[clamp(15rem,24vw,22rem)]"> ...
const mono = JetBrains_Mono({ ..., display: "swap",
  fallback: ["ui-monospace", "SFMono-Regular", "Consolas", "Menlo", "monospace"],
  adjustFontFallback: false });
```

**A trap while measuring.** On Windows, `next build` (Next 14) wrote an empty font manifest and
the pages had no `<link rel="preload" as="font">`; the Linux build on Railway has them. Without
preload the font arrives later, so local Lighthouse runs looked worse than the real site.
Measure the deployed site, not a local Windows build.

Result, measured with Lighthouse 12 on the deployed site (11 pages on mobile, 3 on desktop):
CLS 0 on every page; performance 91–97 on mobile and 99 on desktop (it was 84 and 93 on the
home page before the fix).
