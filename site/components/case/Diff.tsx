import { diffLines } from "diff";
import { getTranslations } from "next-intl/server";
import { Children, type ReactNode } from "react";

import { highlight } from "@/lib/highlight";

import { readCode } from "./code";
import { CopyButton } from "./CopyButton";

/** Line numbers (1-based) that were removed from `before` and added in `after`. */
export function changedLines(before: string, after: string) {
  const removed = new Set<number>();
  const added = new Set<number>();
  let oldLine = 1;
  let newLine = 1;
  for (const part of diffLines(before, after)) {
    const count = part.count ?? 0;
    for (let i = 0; i < count; i++) {
      if (part.removed) removed.add(oldLine++);
      else if (part.added) added.add(newLine++);
      else {
        oldLine++;
        newLine++;
      }
    }
  }
  return { removed, added };
}

/**
 * Before / after view for the "Bug I found and fixed" block. In MDX it wraps two fenced code
 * blocks: the first is the old code, the second the fixed code. Changed lines are tinted.
 */
export async function Diff({ children }: { children: ReactNode }) {
  const t = await getTranslations("case.bug");
  const blocks = Children.toArray(children)
    .map(readCode)
    .filter((b) => b !== null);
  if (blocks.length !== 2) {
    throw new Error("<Diff> needs exactly two code blocks: before and after");
  }
  const [before, after] = blocks;
  const { removed, added } = changedLines(before.code, after.code);
  const [beforeHtml, afterHtml] = await Promise.all([
    highlight(before.code, before.lang, { lines: removed, className: "diff-remove" }),
    highlight(after.code, after.lang, { lines: added, className: "diff-add" }),
  ]);

  const panes = [
    { label: t("before"), html: beforeHtml, code: before.code, marker: "−", tone: "bg-accent" },
    { label: t("after"), html: afterHtml, code: after.code, marker: "+", tone: "bg-[#22a05a]" },
  ];

  return (
    <div className="my-6 grid gap-4 xl:grid-cols-2">
      {panes.map((pane) => (
        <figure key={pane.label} className="min-w-0 border border-line bg-surface">
          <figcaption className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <span className="flex items-center gap-2 font-mono text-label uppercase">
              <span aria-hidden="true" className={`h-2 w-2 ${pane.tone}`} />
              {pane.label}
            </span>
            <CopyButton code={pane.code} />
          </figcaption>
          <div dangerouslySetInnerHTML={{ __html: pane.html }} />
        </figure>
      ))}
    </div>
  );
}
