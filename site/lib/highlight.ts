import "server-only";

import { createHighlighterCore, type HighlighterCore, type ShikiTransformer } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";

// Highlighting runs at build time on the server, so visitors download no highlighter at all.
// The JavaScript regex engine avoids loading a WebAssembly file inside Next.js.
let highlighter: Promise<HighlighterCore> | null = null;

function getHighlighter(): Promise<HighlighterCore> {
  highlighter ??= createHighlighterCore({
    themes: [import("@shikijs/themes/github-light"), import("@shikijs/themes/github-dark")],
    langs: [
      import("@shikijs/langs/python"),
      import("@shikijs/langs/typescript"),
      import("@shikijs/langs/tsx"),
      import("@shikijs/langs/yaml"),
      import("@shikijs/langs/bash"),
      import("@shikijs/langs/json"),
      import("@shikijs/langs/toml"),
    ],
    engine: createJavaScriptRegexEngine(),
  });
  return highlighter;
}

const SUPPORTED = new Set(["python", "typescript", "tsx", "yaml", "bash", "json", "toml"]);

/** Mark whole lines (1-based) with a CSS class, e.g. to colour changed lines in a diff. */
function markLines(lines: Set<number>, className: string): ShikiTransformer {
  return {
    name: "mark-lines",
    line(node, line) {
      if (lines.has(line)) this.addClassToHast(node, className);
    },
  };
}

export async function highlight(
  code: string,
  lang: string,
  marked?: { lines: Set<number>; className: string },
): Promise<string> {
  const shiki = await getHighlighter();
  return shiki.codeToHtml(code, {
    lang: SUPPORTED.has(lang) ? lang : "text",
    // Both themes are emitted as CSS variables; globals.css picks one per colour scheme.
    themes: { light: "github-light", dark: "github-dark" },
    defaultColor: false,
    transformers: marked ? [markLines(marked.lines, marked.className)] : [],
  });
}
